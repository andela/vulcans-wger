# -*- coding: utf-8 -*-

# This file is part of wger Workout Manager.
#
# wger Workout Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# wger Workout Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License

import logging
import os

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.template.context_processors import csrf
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils import translation
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User as Django_User, User
from django.contrib.auth.views import login as django_loginview
from django.contrib import messages
from django.views.generic import (
    RedirectView,
    UpdateView,
    DetailView,
    ListView
)
from django.conf import settings
from rest_framework.authtoken.models import Token
import datetime
from fitbit import FitbitOauth2Client, Fitbit
from django.db import IntegrityError

from wger.utils.constants import USER_TAB
from wger.utils.generic_views import WgerFormMixin, WgerMultiplePermissionRequiredMixin
from wger.utils.user_agents import check_request_amazon, check_request_android
from wger.core.forms import (
    UserPreferencesForm,
    UserPersonalInformationForm,
    PasswordConfirmationForm,
    RegistrationForm,
    RegistrationFormNoCaptcha,
    UserLoginForm)
from wger.core.models import Language
from wger.manager.models import (
    WorkoutLog,
    WorkoutSession,
    Workout
)
from wger.nutrition.models import NutritionPlan
from wger.config.models import GymConfig
from wger.weight.models import WeightEntry
from wger.gym.models import (
    AdminUserNote,
    GymUserConfig,
    Contract
)

from wger.exercises.models import (
    Exercise,
    Muscle,
    ExerciseCategory,
)

from wger.core.models import License
from wger.nutrition.models import Ingredient
from wger.utils.helpers import smart_capitalize

logger = logging.getLogger(__name__)

settings.SITE_URL = os.getenv('SITE_URL')


def login(request):
    '''
    Small wrapper around the django login view
    '''

    context = {'active_tab': USER_TAB}
    if request.GET.get('next'):
        context['next'] = request.GET.get('next')

    return django_loginview(request,
                            template_name='user/login.html',
                            authentication_form=UserLoginForm,
                            extra_context=context)


@login_required()
def delete(request, user_pk=None):
    '''
    Delete a user account and all his data, requires password confirmation first

    If no user_pk is present, the user visiting the URL will be deleted, otherwise
    a gym administrator is deleting a different user
    '''

    if user_pk:
        user = get_object_or_404(User, pk=user_pk)
        form_action = reverse('core:user:delete', kwargs={'user_pk': user_pk})

        # Forbidden if the user has not enough rights, doesn't belong to the
        # gym or is an admin as well. General admins can delete all users.
        if not request.user.has_perm('gym.manage_gyms') \
                and (not request.user.has_perm('gym.manage_gym')
                     or request.user.userprofile.gym_id != user.userprofile.gym_id
                     or user.has_perm('gym.manage_gym')
                     or user.has_perm('gym.gym_trainer')
                     or user.has_perm('gym.manage_gyms')):
            return HttpResponseForbidden()
    else:
        user = request.user
        form_action = reverse('core:user:delete')

    form = PasswordConfirmationForm(user=request.user)

    if request.method == 'POST':
        form = PasswordConfirmationForm(data=request.POST, user=request.user)
        if form.is_valid():

            user.delete()
            messages.success(request,
                             _('Account "{0}" was successfully deleted').format(user.username))

            if not user_pk:
                django_logout(request)
                return HttpResponseRedirect(reverse('software:features'))
            else:
                gym_pk = request.user.userprofile.gym_id
                return HttpResponseRedirect(reverse('gym:gym:user-list', kwargs={'pk': gym_pk}))
    context = {'form': form,
               'user_delete': user,
               'form_action': form_action}

    return render(request, 'user/delete_account.html', context)


@login_required()
def trainer_login(request, user_pk):
    '''
    Allows a trainer to 'log in' as the selected user
    '''
    user = get_object_or_404(User, pk=user_pk)
    orig_user_pk = request.user.pk

    # Changing only between the same gym
    if request.user.userprofile.gym != user.userprofile.gym:
        return HttpResponseForbidden()

    # No changing if identity is not set
    if not request.user.has_perm('gym.gym_trainer') \
            and not request.session.get('trainer.identity'):
        return HttpResponseForbidden()

    # Changing between trainers or managers is not allowed
    if request.user.has_perm('gym.gym_trainer') \
            and (user.has_perm('gym.gym_trainer')
                 or user.has_perm('gym.manage_gym')
                 or user.has_perm('gym.manage_gyms')):
        return HttpResponseForbidden()

    # Check if we're switching back to our original account
    own = False
    if (user.has_perm('gym.gym_trainer')
            or user.has_perm('gym.manage_gym')
            or user.has_perm('gym.manage_gyms')):
        own = True

    # Note: it seems we have to manually set the authentication backend here
    # - https://docs.djangoproject.com/en/1.6/topics/auth/default/#auth-web-requests
    # - http://stackoverflow.com/questions/3807777/django-login-without-authenticating
    if own:
        del(request.session['trainer.identity'])
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    django_login(request, user)

    if not own:
        request.session['trainer.identity'] = orig_user_pk
        if request.GET.get('next'):
            return HttpResponseRedirect(request.GET['next'])
        else:
            return HttpResponseRedirect(reverse('core:index'))
    else:
        return HttpResponseRedirect(reverse('gym:gym:user-list',
                                            kwargs={'pk': user.userprofile.gym_id}))


def logout(request):
    '''
    Logout the user. For temporary users, delete them.
    '''
    user = request.user
    django_logout(request)
    if user.is_authenticated() and user.userprofile.is_temporary:
        user.delete()
    return HttpResponseRedirect(reverse('core:user:login'))


def registration(request):
    '''
    A form to allow for registration of new users
    '''

    # If global user registration is deactivated, redirect
    if not settings.WGER_SETTINGS['ALLOW_REGISTRATION']:
        return HttpResponseRedirect(reverse('software:features'))

    template_data = {}
    template_data.update(csrf(request))

    # Don't use captcha when registering through an app
    is_app = check_request_amazon(request) or check_request_android(request)
    FormClass = RegistrationFormNoCaptcha if is_app else RegistrationForm

    # Don't show captcha if the global parameter is false
    if not settings.WGER_SETTINGS['USE_RECAPTCHA']:
        FormClass = RegistrationFormNoCaptcha

    # Redirect regular users, in case they reached the registration page
    if request.user.is_authenticated() and not request.user.userprofile.is_temporary:
        return HttpResponseRedirect(reverse('core:dashboard'))

    if request.method == 'POST':
        form = FormClass(data=request.POST)

        # If the data is valid, log in and redirect
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']
            email = form.cleaned_data['email']
            user = Django_User.objects.create_user(username,
                                                   email,
                                                   password)
            user.save()

            # Pre-set some values of the user's profile
            language = Language.objects.get(
                short_name=translation.get_language())
            user.userprofile.notification_language = language

            # Set default gym, if needed
            gym_config = GymConfig.objects.get(pk=1)
            if gym_config.default_gym:
                user.userprofile.gym = gym_config.default_gym

                # Create gym user configuration object
                config = GymUserConfig()
                config.gym = gym_config.default_gym
                config.user = user
                config.save()

            user.userprofile.save()

            user = authenticate(username=username, password=password)
            django_login(request, user)
            messages.success(request, _('You were successfully registered'))
            return HttpResponseRedirect(reverse('core:dashboard'))
    else:
        form = FormClass()

    template_data['form'] = form
    template_data['title'] = _('Register')
    template_data['form_fields'] = [i for i in form]
    template_data['form_action'] = reverse('core:user:registration')
    template_data['submit_text'] = _('Register')
    template_data['extend_template'] = 'base.html'

    return render(request, 'form.html', template_data)


@login_required
def preferences(request):
    '''
    An overview of all user preferences
    '''
    template_data = {}
    template_data.update(csrf(request))
    redirect = False

    # Process the preferences form
    if request.method == 'POST':

        form = UserPreferencesForm(
            data=request.POST, instance=request.user.userprofile)
        form.user = request.user

        # Save the data if it validates
        if form.is_valid():
            form.save()
            redirect = True
    else:
        form = UserPreferencesForm(instance=request.user.userprofile)

    # Process the email form
    if request.method == 'POST':
        email_form = UserPersonalInformationForm(
            data=request.POST, instance=request.user)

        if email_form.is_valid() and redirect:
            email_form.save()
            redirect = True
        else:
            redirect = False
    else:
        email_form = UserPersonalInformationForm(instance=request.user)

    template_data['form'] = form
    template_data['email_form'] = email_form

    if redirect:
        messages.success(request, _('Settings successfully updated'))
        return HttpResponseRedirect(reverse('core:user:preferences'))
    else:
        return render(request, 'user/preferences.html', template_data)


class UserDeactivateView(LoginRequiredMixin,
                         WgerMultiplePermissionRequiredMixin,
                         RedirectView):
    '''
    Deactivates a user
    '''
    permanent = False
    model = User
    permission_required = (
        'gym.manage_gym', 'gym.manage_gyms', 'gym.gym_trainer')

    def dispatch(self, request, *args, **kwargs):
        '''
        Only managers and trainers for this gym can access the members
        '''
        edit_user = get_object_or_404(User, pk=self.kwargs['pk'])

        if not request.user.is_authenticated():
            return HttpResponseForbidden()

        if (request.user.has_perm('gym.manage_gym') or request.user.has_perm('gym.gym_trainer')) \
                and edit_user.userprofile.gym_id != request.user.userprofile.gym_id:
            return HttpResponseForbidden()

        return super(UserDeactivateView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, pk):
        edit_user = get_object_or_404(User, pk=pk)
        edit_user.is_active = False
        edit_user.save()
        messages.success(self.request, _(
            "The user was successfully deactivated"))
        return reverse('core:user:overview', kwargs=({'pk': pk}))


class UserActivateView(LoginRequiredMixin,
                       WgerMultiplePermissionRequiredMixin,
                       RedirectView):
    '''
    Activates a previously deactivated user
    '''
    permanent = False
    model = User
    permission_required = (
        'gym.manage_gym', 'gym.manage_gyms', 'gym.gym_trainer')

    def dispatch(self, request, *args, **kwargs):
        '''
        Only managers and trainers for this gym can access the members
        '''
        edit_user = get_object_or_404(User, pk=self.kwargs['pk'])

        if not request.user.is_authenticated():
            return HttpResponseForbidden()

        if (request.user.has_perm('gym.manage_gym') or request.user.has_perm('gym.gym_trainer')) \
                and edit_user.userprofile.gym_id != request.user.userprofile.gym_id:
            return HttpResponseForbidden()

        return super(UserActivateView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, pk):
        edit_user = get_object_or_404(User, pk=pk)
        edit_user.is_active = True
        edit_user.save()
        messages.success(self.request, _(
            'The user was successfully activated'))
        return reverse('core:user:overview', kwargs=({'pk': pk}))


class UserEditView(WgerFormMixin,
                   LoginRequiredMixin,
                   WgerMultiplePermissionRequiredMixin,
                   UpdateView):
    '''
    View to update the personal information of a user by an admin
    '''

    model = User
    title = ugettext_lazy('Edit user')
    permission_required = ('gym.manage_gym', 'gym.manage_gyms')
    form_class = UserPersonalInformationForm

    def dispatch(self, request, *args, **kwargs):
        '''
        Check permissions

        - Managers can edit members of their own gym
        - General managers can edit every member
        '''
        user = request.user
        if not user.is_authenticated():
            return HttpResponseForbidden()

        if user.has_perm('gym.manage_gym') \
                and not user.has_perm('gym.manage_gyms') \
                and user.userprofile.gym != self.get_object().userprofile.gym:
            return HttpResponseForbidden()

        return super(UserEditView, self).dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('core:user:overview', kwargs={'pk': self.kwargs['pk']})

    def get_context_data(self, **kwargs):
        '''
        Send some additional data to the template
        '''
        context = super(UserEditView, self).get_context_data(**kwargs)
        context['form_action'] = reverse(
            'core:user:edit', kwargs={'pk': self.object.id})
        context['title'] = _('Edit {0}'.format(self.object))
        return context


@login_required
def api_key(request):
    '''
    Allows the user to generate an API key for the REST API
    '''

    context = {}
    context.update(csrf(request))

    try:
        token = Token.objects.get(user=request.user)
    except Token.DoesNotExist:
        token = False
    if request.GET.get('new_key'):
        if token:
            token.delete()

        token = Token.objects.create(user=request.user)

        # Redirect to get rid of the GET parameter
        return HttpResponseRedirect(reverse('core:user:api-key'))

    context['token'] = token

    return render(request, 'user/api_key.html', context)


class UserDetailView(LoginRequiredMixin, WgerMultiplePermissionRequiredMixin, DetailView):
    '''
    User overview for gyms
    '''
    model = User
    permission_required = (
        'gym.manage_gym', 'gym.manage_gyms', 'gym.gym_trainer')
    template_name = 'user/overview.html'
    context_object_name = 'current_user'

    def dispatch(self, request, *args, **kwargs):
        '''
        Check permissions

        - Only managers for this gym can access the members
        - General managers can access the detail page of all users
        '''
        user = request.user

        if not user.is_authenticated():
            return HttpResponseForbidden()

        if (user.has_perm('gym.manage_gym') or user.has_perm('gym.gym_trainer')) \
                and not user.has_perm('gym.manage_gyms') \
                and user.userprofile.gym != self.get_object().userprofile.gym:
            return HttpResponseForbidden()

        return super(UserDetailView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        '''
        Send some additional data to the template
        '''
        context = super(UserDetailView, self).get_context_data(**kwargs)
        out = []
        workouts = Workout.objects.filter(user=self.object).all()
        for workout in workouts:
            logs = WorkoutLog.objects.filter(workout=workout)
            out.append({'workout': workout,
                        'logs': logs.dates('date', 'day').count(),
                        'last_log': logs.last()})
        context['workouts'] = out
        context['weight_entries'] = WeightEntry.objects.filter(user=self.object)\
            .order_by('-date')[:5]
        context['nutrition_plans'] = NutritionPlan.objects.filter(user=self.object)\
            .order_by('-creation_date')[:5]
        context['session'] = WorkoutSession.objects.filter(
            user=self.object).order_by('-date')[:10]
        context['admin_notes'] = AdminUserNote.objects.filter(member=self.object)[
            :5]
        context['contracts'] = Contract.objects.filter(member=self.object)[:5]
        return context


def fitbit_authorize(callback):
    client_id = settings.WGER_SETTINGS['FITBIT_CLIENT_ID']
    client_secret = settings.WGER_SETTINGS['FITBIT_CLIENT_SECRET']
    call_back = callback
    fitbit_client = FitbitOauth2Client(client_id, client_secret)
    url = fitbit_client.authorize_token_url(redirect_uri=call_back, prompt='login')

    template = {"fitbit_url": url[0]}
    return template


def fitbit_get_info(code, callback, action=None):
    try:
        client_id = settings.WGER_SETTINGS['FITBIT_CLIENT_ID']
        client_secret = settings.WGER_SETTINGS['FITBIT_CLIENT_SECRET']
        fitbit_client = FitbitOauth2Client(client_id, client_secret)
        call_back = callback
        token = fitbit_client.fetch_access_token(code, redirect_uri=call_back)
        if "access_token" in token:
            fitbit_request = Fitbit(client_id=client_id, client_secret=client_secret,
                                    access_token=token["access_token"],
                                    refresh_token=token["refresh_token"], system="en_UK")
            if action == 'weight':
                return fitbit_request.user_profile_get()
            elif action == 'exercise':
                return fitbit_request.activities_list()
            elif action == 'food_log':
                return fitbit_request._COLLECTION_RESOURCE('foods/log')
    except BaseException as e:
        return str(e)


@login_required
def sync_fitbit_weight(request):
    '''
    Integrates with fitbit to fetch weight.
    '''
    call_back = settings.SITE_URL + reverse('core:user:fitbit-weight')
    template = fitbit_authorize(call_back)
    if "code" in request.GET:
        token_code = request.GET["code"]
        user_prof = fitbit_get_info(token_code, call_back, action='weight')
        weight = user_prof["user"]["weight"]
        try:
            fetched_weight = WeightEntry()
            fetched_weight.weight = weight
            fetched_weight.user = request.user
            fetched_weight.date = datetime.date.today()
            fetched_weight.save()
            messages.success(request, _('Successfully synced weight data.'))
            return HttpResponseRedirect(
                reverse('weight:overview', kwargs={
                    'username': request.user.username}))
        except IntegrityError as e:

            if "UNIQUE CONSTRAINT" in str(e).upper():
                messages.info(request, _('Already synced up for today.'))
                return HttpResponseRedirect(
                    reverse('weight:overview', kwargs={
                        'username': request.user.username}))

            messages.warning(request, _("Something went wrong") + str(e))

            return render(request, 'user/fitbit_weight_info.html', template)

    return render(request, 'user/fitbit_weight_info.html', template)


@login_required
def sync_fitbit_activity(request):
    '''
    Integrate with fitbit to get activities
    '''

    call_back = settings.SITE_URL + reverse('core:user:fitbit-activity')
    template = fitbit_authorize(call_back)
    if "code" in request.GET:
        token_code = request.GET["code"]
        response = fitbit_get_info(token_code, call_back, action='exercise')

        activities = []
        for category in response['categories']:
            for item in category.get('activities'):
                activities.append(item.get('name'))
        try:
            if not activities:
                messages.info(request, _('Sorry no activity logged on Fitbit today'))
                return HttpResponseRedirect(
                    reverse('exercise:exercise:overview'))

            if not ExerciseCategory.objects.filter(name='Fitbit').exists():
                exercise_category = ExerciseCategory()
                exercise_category.name = 'Fitbit'
                exercise_category.save()

            for name in activities:
                name_original = smart_capitalize(name)
                exercise = Exercise()
                if not Exercise.objects.filter(name=name_original).exists():
                    exercise.name_original = name
                    exercise.description = name_original
                    exercise.language = Language.objects.get(short_name='en')
                    if not License.objects.filter(short_name='Apache').exists():
                        licence = License(short_name="Apache", full_name='Apache License Version'
                                                                         '2.0,January 2004',
                                          url='http://www.apache.org/licenses/LICENSE-2.0')
                        licence.save()
                    exercise.license = License.objects.get(short_name='Apache')
                    exercise.category = ExerciseCategory.objects.get(
                        name='Fitbit')
                    exercise.set_author(request)
                    exercise.save()
                    messages.success(request, _('Successfully synced exercise data.'))
                    return HttpResponseRedirect(
                        reverse('exercise:exercise:overview'))
                else:
                    messages.info(request, _('Already synced up exercises for today.'))

                    return HttpResponseRedirect(
                        reverse('exercise:exercise:overview'))

        except BaseException as e:
            messages.warning(request, _("Something went wrong") + str(e))
            return render(request, 'user/fitbit_activity_info.html', template)

    return render(request, 'user/fitbit_activity_info.html', template)


@login_required
def sync_fitbit_nutrition_info(request):
    '''
    Integrates with fitbit to get nutrition information
    '''

    call_back = settings.SITE_URL + reverse('core:user:fitbit-ingredients')

    template = fitbit_authorize(call_back)
    if "code" in request.GET:
        token_code = request.GET["code"]
        food_collection = fitbit_get_info(token_code, call_back, action='food_log')
        if food_collection:
            for item in food_collection['foods']:
                logged_food_names = item.get('loggedFood').get('name')
                if not logged_food_names:
                    messages.info(request, _('Sorry no food logs on Fitbit today'))
                    return HttpResponseRedirect(
                        reverse('nutrition:ingredient:list'))
                nutrition_values = item.get('nutritionalValues')
                if nutrition_values:
                    calories = nutrition_values.get('calories', 0)
                    carbs = nutrition_values.get('carbs', 0)
                    fat = nutrition_values.get('fat', 0)
                    fiber = nutrition_values.get('fiber', 0)
                    protein = nutrition_values.get('protein', 0)
                    sodium = nutrition_values.get('sodium', 0)

                else:
                    calories, carbs, fat, fiber, protein, sodium = [0, 0, 0, 0, 0, 0]

                try:
                    new_ingredient = Ingredient()
                    if not Ingredient.objects.filter(name=logged_food_names).exists():
                        new_ingredient.user = request.user
                        new_ingredient.name = logged_food_names
                        new_ingredient.carbohydrates = carbs
                        new_ingredient.fat = fat
                        new_ingredient.fibres = fiber
                        new_ingredient.protein = protein
                        new_ingredient.sodium = sodium
                        new_ingredient.energy = calories
                        new_ingredient.language = Language.objects.get(short_name='en')
                        new_ingredient.save()
                        messages.success(request, _('Successfully synced your Food Logs'))
                        return HttpResponseRedirect(
                            reverse('nutrition:ingredient:list'))
                    else:
                        messages.info(request, _('Already synced up Ingredients for today.'))
                        return HttpResponseRedirect(
                            reverse('nutrition:ingredient:list'))
                except BaseException as e:
                    messages.warning(request, _('Something went wrong ') + str(e))
        else:
            messages.info(request, _('You have no food collections today.'))
            return HttpResponseRedirect(
                reverse('nutrition:ingredient:list'))
    return render(request, 'user/fitbit_nutrition_info.html', template)


class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    '''
    Overview of all users in the instance
    '''
    model = User
    permission_required = ('gym.manage_gyms',)
    template_name = 'user/list.html'

    def get_queryset(self):
        '''
        Return a list with the users, not really a queryset.
        '''
        out = {'admins': [],
               'active_members': [],
               'deactive_members': []}

        for u in User.objects.select_related('usercache',
                                             'userprofile__gym').filter(is_active=True):
            out['active_members'].append({'obj': u,
                                          'last_log': u.usercache.last_activity})
        for u in User.objects.select_related('usercache',
                                             'userprofile__gym').filter(is_active=False):
            out['deactive_members'].append({'obj': u,
                                            'last_log': u.usercache.last_activity})

        return out

    def get_context_data(self, **kwargs):
        '''
        Pass other info to the template
        '''
        context = super(UserListView, self).get_context_data(**kwargs)
        context['show_gym'] = True
        context['user_table'] = {'keys': [_('ID'),
                                          _('Username'),
                                          _('Name'),
                                          _('Last activity'),
                                          _('Gym')],
                                 'users': context['object_list']['active_members'],
                                 'deactive_users': context['object_list']['deactive_members']}
        return context

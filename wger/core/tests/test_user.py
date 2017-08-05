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
import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse, reverse_lazy
from mock import patch

from wger.core.tests.base_testcase import (
    WorkoutManagerTestCase,
    WorkoutManagerEditTestCase,
    WorkoutManagerAccessTestCase
)

from wger.exercises.models import (
    Exercise,
    ExerciseCategory
)

from wger.nutrition.models import Ingredient
from wger.weight.models import WeightEntry


class StatusUserTestCase(WorkoutManagerTestCase):
    '''
    Test activating and deactivating users
    '''

    user_success = ('general_manager1',
                    'general_manager2',
                    'manager1',
                    'manager2',
                    'trainer1',
                    'trainer2',
                    'trainer3')

    user_fail = ('member1',
                 'member2',
                 'member3',
                 'member4',
                 'manager3',
                 'trainer4')

    def activate(self, fail=False):
        '''
        Helper function to test activating users
        '''
        user = User.objects.get(pk=2)
        user.is_active = False
        user.save()
        self.assertFalse(user.is_active)

        response = self.client.get(
            reverse('core:user:activate', kwargs={'pk': user.pk}))
        user = User.objects.get(pk=2)

        self.assertIn(response.status_code, (302, 403))
        if fail:
            self.assertFalse(user.is_active)
        else:
            self.assertTrue(user.is_active)

    def test_activate_authorized(self):
        '''
        Tests activating a user as an administrator
        '''
        for username in self.user_success:
            self.user_login(username)
            self.activate()
            self.user_logout()

    def test_activate_unauthorized(self):
        '''
        Tests activating a user as another logged in user
        '''
        for username in self.user_fail:
            self.user_login(username)
            self.activate(fail=True)
            self.user_logout()

    def test_activate_logged_out(self):
        '''
        Tests activating a user a logged out user
        '''
        self.activate(fail=True)

    def deactivate(self, fail=False):
        '''
        Helper function to test deactivating users
        '''
        user = User.objects.get(pk=2)
        user.is_active = True
        user.save()
        self.assertTrue(user.is_active)

        response = self.client.get(
            reverse('core:user:deactivate', kwargs={'pk': user.pk}))
        user = User.objects.get(pk=2)

        self.assertIn(response.status_code, (302, 403))
        if fail:
            self.assertTrue(user.is_active)
        else:
            self.assertFalse(user.is_active)

    def test_deactivate_authorized(self):
        '''
        Tests deactivating a user as an administrator
        '''
        for username in self.user_success:
            self.user_login(username)
            self.deactivate()
            self.user_logout()

    def test_deactivate_unauthorized(self):
        '''
        Tests deactivating a user as another logged in user
        '''
        for username in self.user_fail:
            self.user_login(username)
            self.deactivate(fail=True)
            self.user_logout()

    def test_deactivate_logged_out(self):
        '''
        Tests deactivating a user a logged out user
        '''
        self.deactivate(fail=True)


class EditUserTestCase(WorkoutManagerEditTestCase):
    '''
    Test editing a user
    '''

    object_class = User
    url = 'core:user:edit'
    pk = 2
    data = {'email': 'another.email@example.com',
            'first_name': 'Name',
            'last_name': 'Last name'}
    user_success = ('admin',
                    'general_manager1',
                    'general_manager2',
                    'manager1',
                    'manager2')
    user_fail = ('member1',
                 'member2',
                 'manager3',
                 'trainer2',
                 'trainer3',
                 'trainer4')


class EditUserTestCase2(WorkoutManagerEditTestCase):
    '''
    Test editing a user
    '''

    object_class = User
    url = 'core:user:edit'
    pk = 19
    data = {'email': 'another.email@example.com',
            'first_name': 'Name',
            'last_name': 'Last name'}
    user_success = ('admin',
                    'general_manager1',
                    'general_manager2',
                    'manager3')
    user_fail = ('member1',
                 'member2',
                 'trainer2',
                 'trainer3',
                 'trainer4')


class UserListTestCase(WorkoutManagerAccessTestCase):
    '''
    Test accessing the general user overview
    '''

    url = 'core:user:list'
    user_success = ('admin',
                    'general_manager1',
                    'general_manager2')
    user_fail = ('member1',
                 'member2',
                 'manager1',
                 'manager2',
                 'manager3',
                 'trainer2',
                 'trainer3',
                 'trainer4')


class UserDetailPageTestCase(WorkoutManagerAccessTestCase):
    '''
    Test accessing the user detail page
    '''

    url = reverse_lazy('core:user:overview', kwargs={'pk': 2})
    user_success = ('trainer1',
                    'trainer2',
                    'manager1',
                    'general_manager1',
                    'general_manager2')
    user_fail = ('trainer4',
                 'trainer5',
                 'manager3',
                 'member1',
                 'member2')


class UserDetailPageTestCase2(WorkoutManagerAccessTestCase):
    '''
    Test accessing the user detail page
    '''

    url = reverse_lazy('core:user:overview', kwargs={'pk': 19})
    user_success = ('trainer4',
                    'trainer5',
                    'manager3',
                    'general_manager1',
                    'general_manager2')
    user_fail = ('trainer1',
                 'trainer2',
                 'manager1',
                 'member1',
                 'member2')


class UserFitbitSyncTestCase(WorkoutManagerTestCase):
    '''
    Test fitbit integration.
    '''
    def setUp(self):
        self.username = 'test'
        self.password = 'test'
        self.code = {'code': 'some-test-code'}
        self.call_back_weight = settings.SITE_URL + reverse('core:user:fitbit')
        self.call_back_exercise = settings.SITE_URL + reverse('core:user:fitbit-activity')
        self.call_back_ingredients = settings.SITE_URL + reverse('core:user:fitbit-ingredients')
        os.environ['RECAPTCHA_TESTING'] = 'True'

    def tearDown(self):
        del os.environ['RECAPTCHA_TESTING']

    @patch('wger.core.views.user.fitbit_get_data')
    def test_sync_fitbit_weight(self, mock_fitbit_info):
        initial_weight_entry_count = WeightEntry.objects.count()
        user_info = {"user": {"weight": 68}}
        mock_fitbit_info.return_value = user_info
        self.client.post(reverse('core:user:login'),
                         data={'username': self.username, 'password': self.password})
        response = self.client.get(reverse('core:user:fitbit'),
                                   data=self.code)

        self.assertRedirects(response, reverse('weight:overview',
                                               kwargs={'username': self.username}))
        final_weight_entry_count = WeightEntry.objects.count()
        self.assertEqual((final_weight_entry_count - initial_weight_entry_count), 1)

    @patch('wger.core.views.user.fitbit_get_data')
    def test_sync_fitbit_ingredients(self, mock_fitbit_data):
        initial_ingredient_count = Ingredient.objects.count()
        data = {"foods": [{"loggedFood": {"name": "Croissant"},
                           "nutritionalValues": {"calories": 293, "carbs": 30.86, "fat": 15.96,
                                                 "fiber": 0.96, "protein": 5.19, "sodium": 235}}]}
        mock_fitbit_data.return_value = data
        self.client.post(reverse('core:user:login'),
                         data={'username': self.username, 'password': self.password})
        response = self.client.get(reverse('core:user:fitbit-ingredients'),
                                   data=self.code, follow=True)

        self.assertContains(response, 'Successfully synced your Food Log')
        self.assertRedirects(response, reverse('nutrition:ingredient:list'))
        final_ingredient_count = Ingredient.objects.count()
        self.assertEqual((final_ingredient_count - initial_ingredient_count), 1)

    def test_sync_fitbit_exercise(self, mock_fitbit_data):
        initial_exercise_count = Exercise.objects.count()
        initial_exercise_category_count = ExerciseCategory.objects.count()
        activity = {"categories": [{"activities": [{"name": "Aerobic step"}], "name": "Dancing"}]}

        mock_fitbit_data.return_value = activity
        self.client.post(reverse('core:user:login'),
                         data={'username': self.username, 'password': self.password})
        response = self.client.get(reverse('core:user:fitbit-activity'),
                                   data=self.code, follow=True)
        self.assertRedirects(response, reverse('exercise:exercise:overview'))
        self.assertContains(response, 'Successfully synced exercise data.')
        final_exercise_count = Exercise.objects.count()
        final_exercise_category_count = ExerciseCategory.objects.count()
        self.assertEqual((final_exercise_count - initial_exercise_count), 1)
        self.assertEqual((final_exercise_category_count - initial_exercise_category_count), 1)
        category_obj = ExerciseCategory.objects.all()
        category_names = [n.name for n in category_obj]
        self.assertIn('Fitbit', category_names)

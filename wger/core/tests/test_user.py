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

from wger.core.views.user import fitbit_authorize, fitbit_get_info
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
        self.password = 'testtest'
        self.code = {'code': '80b5a817c2b1d8fb2081db8d31d870446828017'}
        self.call_back_weight = settings.SITE_URL + reverse('core:user:fitbit-weight')
        self.call_back_exercise = settings.SITE_URL + reverse('core:user:fitbit-activity')
        self.call_back_ingredients = settings.SITE_URL + reverse('core:user:fitbit-ingredients')
        os.environ['RECAPTCHA_TESTING'] = 'True'

    def tearDown(self):
        del os.environ['RECAPTCHA_TESTING']

    @patch('wger.core.views.user.fitbit_get_info')
    def test_sync_fitbit_weight(self, mock_fitbit_data):
        initial_weight_entry_count = WeightEntry.objects.count()
        user_info = {"user": {"weight": 70}}
        mock_fitbit_data.return_value = user_info
        self.client.post(reverse('core:user:login'),
                         data={'username': self.username, 'password': self.password})
        response = self.client.get(reverse('core:user:fitbit-weight'),
                                   data=self.code)

        self.assertRedirects(response, reverse('weight:overview',
                                               kwargs={'username': self.username}))
        final_weight_entry_count = WeightEntry.objects.count()
        self.assertEqual((final_weight_entry_count - initial_weight_entry_count), 1)

    @patch('wger.core.views.user.fitbit_get_info')
    def test_sync_fitbit_nutrition_info(self, mock_fitbit_data):
        initial_ingredient_count = Ingredient.objects.count()
        nutritional_info = {"foods": [{"loggedFood": {"name": "Croissant"}, "nutritionalValues": {
            "calories": 300, "carbs": 50.75, "fat": 17.05, "fiber": 0.16, "protein": 4.35,
            "sodium": 200}}]}
        mock_fitbit_data.return_value = nutritional_info
        self.client.post(reverse('core:user:login'),
                         data={'username': self.username, 'password': self.password})
        response = self.client.get(reverse('core:user:fitbit-ingredients'),
                                   data=self.code, follow=True)

        self.assertContains(response, 'Successfully synced your Food Log')
        self.assertRedirects(response, reverse('nutrition:ingredient:list'))
        final_ingredient_count = Ingredient.objects.count()
        self.assertEqual((final_ingredient_count - initial_ingredient_count), 1)

    @patch('wger.core.views.user.fitbit_get_info')
    def test_sync_fitbit_activity(self, mock_fitbit_data):
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

    def test_fitbit_authorize(self):
        with self.settings(WGER_SETTINGS={'FITBIT_CLIENT_ID': 'fake-client-id',
                                          'FITBIT_CLIENT_SECRET': 'fake-client-secret',
                                          'USE_RECAPTCHA': False,
                                          'REMOVE_WHITESPACE': False,
                                          'ALLOW_REGISTRATION': True,
                                          'ALLOW_GUEST_USERS': True,
                                          'EMAIL_FROM': 'wger Workout Manager <wger@example.com>',
                                          'TWITTER': False
                                          }):
            with self.settings(SITE_URL='http://localhost:8000'):
                template = fitbit_authorize(self.call_back_weight)
                expected_response = 'https://www.fitbit.com/oauth2/authorize?response_type=code&' \
                                    'client_id=fake-client-id&redirect_uri=https%3A%2F%2F' \
                                    'vulcanswger-pr-10.herokuapp.com%2Fen%2Fuser%2F' \
                                    'fitbit_sync_weight&scope=activity+nutrition+heartrate+' \
                                    'location+ nutrition+profile+settings+sleep+social+' \
                                    'weight&state=YducaIA6Dv1NpTrs8SyYF78p7XDrno&prompt=login'
                self.assertIn('https://www.fitbit.com/oauth2/authorize?response_type=code&'
                              'client_id=fake-client-id&redirect_uri=https%3A%2F%2F'
                              'vulcanswger-pr-10.herokuapp.com%2Fen%2Fuser%2F', expected_response)
                self.assertIn('prompt=login', template['fitbit_url'])

    @patch('fitbit.Fitbit._COLLECTION_RESOURCE')
    @patch('fitbit.Fitbit.activities_list')
    @patch('fitbit.Fitbit.user_profile_get')
    @patch('fitbit.FitbitOauth2Client.fetch_access_token')
    def test_sync_fitbit_get_info(self, mock_fetch_access_token, mock_user_profile_get,
                                  mock_activities_list, mock_COLLECTION_RESOURCE):
        token = {'access_token': '215516887', 'refresh_token': '215516887215516887'}
        mock_fetch_access_token.return_value = token
        user_info = {"user": {"weight": 70}}
        mock_user_profile_get.return_value = user_info
        activity = {"categories": [{"activities": [{"name": "Aerobic step"}], "name": "Dancing"}]}
        mock_activities_list.return_value = activity
        nutritional_info = {"foods": [{"loggedFood": {"name": "Croissant"}, "nutritionalValues": {
            "calories": 300, "carbs": 50.75, "fat": 17.05, "fiber": 0.16, "protein": 4.35,
            "sodium": 200}}]}
        mock_COLLECTION_RESOURCE.return_value = nutritional_info
        with self.settings(WGER_SETTINGS={'FITBIT_CLIENT_ID': 'fake-client-id',
                                          'FITBIT_CLIENT_SECRET': 'fake-client-secret',
                                          'USE_RECAPTCHA': False,
                                          'REMOVE_WHITESPACE': False,
                                          'ALLOW_REGISTRATION': True,
                                          'ALLOW_GUEST_USERS': True,
                                          'EMAIL_FROM': 'wger Workout Manager <wger@example.com>',
                                          'TWITTER': False
                                          }):
            with self.settings(SITE_URL='http://localhost:8000'):
                fitbit_get_info(self.code, self.call_back_weight, action='weight')
                mock_fetch_access_token.assert_called_once_with(self.code,
                                                                redirect_uri=self.call_back_weight)
                mock_user_profile_get.assert_called()
                mock_activities_list.assert_not_called()
                mock_COLLECTION_RESOURCE.assert_not_called()

                fitbit_get_info(self.code, self.call_back_exercise, action='exercise')
                mock_fetch_access_token.assert_called_with(self.code,
                                                           redirect_uri=self.call_back_exercise)
                mock_activities_list.assert_called()
                mock_COLLECTION_RESOURCE.assert_not_called()
                fitbit_get_info(self.code, self.call_back_ingredients, action='food_log')
                mock_fetch_access_token.assert_called_with(self.code,
                                                           redirect_uri=self.call_back_ingredients)
                mock_COLLECTION_RESOURCE.assert_called_with('foods/log')

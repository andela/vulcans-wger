# -*- coding: utf-8 *-*

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

import datetime

from django.template import loader
from django.core.management.base import BaseCommand
from django.core import mail
from django.utils.translation import ugettext_lazy as _
from django.utils import translation
from django.conf import settings
from django.contrib.auth.models import User

from django.contrib.sites.models import Site
from wger.core.models import UserProfile
from wger.manager.models import Schedule


class Command(BaseCommand):
    '''
    Helper admin command to list all the users created by a certain user
    '''

    help = 'List all users created by a certain user'

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', type=str)

    def handle(self, **options):
        '''
        Find if the currently the consumer can create users
        '''
        username = options.get("username", None)

        try:
            users = UserProfile.objects.all().filter(created_by=username)
            if len(users) < 1:
                return 'No users created by {}'.format(username)

            elif len(users) > 0:
                print('The users created by {} are: '.format(username))
                for user in users:
                    print('\t' + user.username)

        except:
            print('User {} not found'.format(username))

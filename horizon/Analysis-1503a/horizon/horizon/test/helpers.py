# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import os
import socket

from django.contrib.auth.middleware import AuthenticationMiddleware  # noqa
from django.contrib.auth.models import Permission  # noqa
from django.contrib.auth.models import User  # noqa
from django.contrib.contenttypes.models import ContentType  # noqa
from django.contrib.messages.storage import default_storage  # noqa
from django.core.handlers import wsgi
from django import http
from django import test as django_test
from django.test.client import RequestFactory  # noqa
from django.utils import unittest

LOG = logging.getLogger(__name__)


try:
    from selenium.webdriver.firefox.webdriver import WebDriver  # noqa
    from selenium.webdriver.support import ui as selenium_ui
except ImportError as e:
    # NOTE(saschpe): Several distribution can't ship selenium due to its
    # non-free license. So they have to patch it out of test-requirements.txt
    # Avoid import failure and force not running selenium tests.
    LOG.warning("{0}, force WITH_SELENIUM=False".format(str(e)))
    os.environ['WITH_SELENIUM'] = ''


import mox

from horizon import middleware


# Makes output of failing mox tests much easier to read.
wsgi.WSGIRequest.__repr__ = lambda self: "<class 'django.http.HttpRequest'>"


class RequestFactoryWithMessages(RequestFactory):
    def get(self, *args, **kwargs):
        req = super(RequestFactoryWithMessages, self).get(*args, **kwargs)
        req.user = User()
        req.session = {}
        req._messages = default_storage(req)
        return req

    def post(self, *args, **kwargs):
        req = super(RequestFactoryWithMessages, self).post(*args, **kwargs)
        req.user = User()
        req.session = {}
        req._messages = default_storage(req)
        return req


@unittest.skipIf(os.environ.get('SKIP_UNITTESTS', False),
                     "The SKIP_UNITTESTS env variable is set.")
class TestCase(django_test.TestCase):
    """Specialized base test case class for Horizon which gives access to
    numerous additional features:

      * The ``mox`` mocking framework via ``self.mox``.
      * A ``RequestFactory`` class which supports Django's ``contrib.messages``
        framework via ``self.factory``.
      * A ready-to-go request object via ``self.request``.
    """
    def setUp(self):
        self.mox = mox.Mox()
        self.factory = RequestFactoryWithMessages()
        self.user = User.objects.create_user(username='test', password='test')
        self.assertTrue(self.client.login(username="test", password="test"))

        self.request = http.HttpRequest()
        self.request.session = self.client._session()
        middleware.HorizonMiddleware().process_request(self.request)
        AuthenticationMiddleware().process_request(self.request)
        os.environ["HORIZON_TEST_RUN"] = "True"

    def tearDown(self):
        self.mox.UnsetStubs()
        self.mox.VerifyAll()
        del os.environ["HORIZON_TEST_RUN"]

    def set_permissions(self, permissions=None):
        perm_ids = Permission.objects.values_list('id', flat=True)
        self.user.user_permissions.remove(*perm_ids)
        for name in permissions:
            ct, create = ContentType.objects.get_or_create(model=name,
                                                           app_label='horizon')
            perm, create = Permission.objects.get_or_create(codename=name,
                                                            content_type=ct,
                                                            name=name)
            self.user.user_permissions.add(perm)
        if hasattr(self.user, "_perm_cache"):
            del self.user._perm_cache

    def assertNoMessages(self, response=None):
        """Asserts that no messages have been attached by the
        ``contrib.messages`` framework.
        """
        self.assertMessageCount(response, success=0, warn=0, info=0, error=0)

    def assertMessageCount(self, response=None, **kwargs):
        """Asserts that the specified number of messages have been attached
        for various message types. Usage would look like
        ``self.assertMessageCount(success=1)``.
        """
        temp_req = self.client.request(**{'wsgi.input': None})
        temp_req.COOKIES = self.client.cookies
        storage = default_storage(temp_req)
        messages = []

        if response is None:
            # To gain early access to the messages we have to decode the
            # cookie on the test client.
            if 'messages' in self.client.cookies:
                message_cookie = self.client.cookies['messages'].value
                messages = storage._decode(message_cookie)
        # Check for messages in the context
        elif hasattr(response, "context") and "messages" in response.context:
            messages = response.context["messages"]
        # Check for messages attached to the request on a TemplateResponse
        elif hasattr(response, "_request") and hasattr(response._request,
                                                       "_messages"):
            messages = response._request._messages._queued_messages

        # If we don't have messages and we don't expect messages, we're done.
        if not any(kwargs.values()) and not messages:
            return

        # If we expected messages and have none, that's a problem.
        if any(kwargs.values()) and not messages:
            error_msg = "Messages were expected, but none were set."
            assert 0 == sum(kwargs.values()), error_msg

        # Otherwise, make sure we got the expected messages.
        for msg_type, count in kwargs.items():
            msgs = [m.message for m in messages if msg_type in m.tags]
            assert len(msgs) == count, \
                   "%s messages not as expected: %s" % (msg_type.title(),
                                                        ", ".join(msgs))


@unittest.skipUnless(os.environ.get('WITH_SELENIUM', False),
                     "The WITH_SELENIUM env variable is not set.")
class SeleniumTestCase(django_test.LiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('WITH_SELENIUM', False):
            cls.selenium = WebDriver()
        super(SeleniumTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('WITH_SELENIUM', False):
            cls.selenium.quit()
        super(SeleniumTestCase, cls).tearDownClass()

    def setUp(self):
        socket.setdefaulttimeout(10)
        self.ui = selenium_ui
        super(SeleniumTestCase, self).setUp()


class JasmineTests(SeleniumTestCase):
    """Helper class which allows you to create a simple Jasmine test running
    through Selenium

    To run a jasmine test suite create a class which extends JasmineTests in
    the :file:`horizon/test/jasmine/jasmine_tests.py` and define two class
    attributes

    .. attribute:: sources

        A list of of JS source files (the {{STATIC_URL}} will be added
        automatically, these are the source files tested

    .. attribute:: specs

        A list of of Jasmine JS spec files (the {{STATIC_URL}} will be added
        automatically

    .. attribute:: template_name

        A template which will contain the html needed by the test,
        this attribute is optional, if it is not specified the default template
        will be used. The template, if specified, must extends
        :file:`horizon/jasmine/jasmine.html` and insert the html in a block
        which name must be content
    """
    sources = []
    specs = []
    template_name = None

    def run_jasmine(self):
        self.selenium.get(
            "%s%s%s" % (self.live_server_url,
                        "/jasmine/",
                        self.__class__.__name__))

        wait = self.ui.WebDriverWait(self.selenium, 120)

        def jasmine_done(driver):
            text = driver.find_element_by_class_name("duration").text
            return "finished" in text

        wait.until(jasmine_done)
        failures = \
            self.selenium.find_elements_by_css_selector(".specDetail.failed")

        results = []
        for failure in failures:
            results.append(
                failure.find_element_by_class_name("description").text)
            results.append(
                failure.find_element_by_class_name("stackTrace").text)

        self.assertEqual(results, [], '\n\n' + '\n\n'.join(results) + '\n\n')

    def test(self):
        if self.__class__ == JasmineTests:
            return
        self.run_jasmine()

#   Copyright 2013 Nebula Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

import copy
import io
import os
import tempfile
from unittest import mock

from openstack import exceptions as sdk_exceptions
from osc_lib.cli import format_columns
from osc_lib import exceptions

from openstackclient.image.v2 import image
from openstackclient.tests.unit.identity.v3 import fakes as identity_fakes
from openstackclient.tests.unit.image.v2 import fakes as image_fakes


class TestImage(image_fakes.TestImagev2):

    def setUp(self):
        super(TestImage, self).setUp()

        # Get shortcuts to mocked image client
        self.client = self.app.client_manager.image

        # Get shortcut to the Mocks in identity client
        self.project_mock = self.app.client_manager.identity.projects
        self.project_mock.reset_mock()
        self.domain_mock = self.app.client_manager.identity.domains
        self.domain_mock.reset_mock()

    def setup_images_mock(self, count):
        images = image_fakes.create_images(count=count)

        return images


class TestImageCreate(TestImage):

    project = identity_fakes.FakeProject.create_one_project()
    domain = identity_fakes.FakeDomain.create_one_domain()

    def setUp(self):
        super(TestImageCreate, self).setUp()

        self.new_image = image_fakes.create_one_image()
        self.client.create_image.return_value = self.new_image

        self.project_mock.get.return_value = self.project

        self.domain_mock.get.return_value = self.domain

        self.client.update_image.return_value = self.new_image

        (self.expected_columns, self.expected_data) = zip(
            *sorted(image._format_image(self.new_image).items()))

        # Get the command object to test
        self.cmd = image.CreateImage(self.app, None)

    @mock.patch("sys.stdin", side_effect=[None])
    def test_image_reserve_no_options(self, raw_input):
        arglist = [
            self.new_image.name
        ]
        verifylist = [
            ('container_format', image.DEFAULT_CONTAINER_FORMAT),
            ('disk_format', image.DEFAULT_DISK_FORMAT),
            ('name', self.new_image.name),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class ShowOne in cliff, abstract method take_action()
        # returns a two-part tuple with a tuple of column names and a tuple of
        # data to be shown.
        columns, data = self.cmd.take_action(parsed_args)

        # ImageManager.create(name=, **)
        self.client.create_image.assert_called_with(
            name=self.new_image.name,
            allow_duplicates=True,
            container_format=image.DEFAULT_CONTAINER_FORMAT,
            disk_format=image.DEFAULT_DISK_FORMAT,
        )

        # Verify update() was not called, if it was show the args
        self.assertEqual(self.client.update_image.call_args_list, [])

        self.assertEqual(
            self.expected_columns,
            columns)
        self.assertCountEqual(
            self.expected_data,
            data)

    @mock.patch('sys.stdin', side_effect=[None])
    def test_image_reserve_options(self, raw_input):
        arglist = [
            '--container-format', 'ovf',
            '--disk-format', 'ami',
            '--min-disk', '10',
            '--min-ram', '4',
            ('--protected'
                if self.new_image.is_protected else '--unprotected'),
            ('--private'
                if self.new_image.visibility == 'private' else '--public'),
            '--project', self.new_image.owner_id,
            '--project-domain', self.domain.id,
            self.new_image.name,
        ]
        verifylist = [
            ('container_format', 'ovf'),
            ('disk_format', 'ami'),
            ('min_disk', 10),
            ('min_ram', 4),
            ('protected', self.new_image.is_protected),
            ('unprotected', not self.new_image.is_protected),
            ('public', self.new_image.visibility == 'public'),
            ('private', self.new_image.visibility == 'private'),
            ('project', self.new_image.owner_id),
            ('project_domain', self.domain.id),
            ('name', self.new_image.name),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class ShowOne in cliff, abstract method take_action()
        # returns a two-part tuple with a tuple of column names and a tuple of
        # data to be shown.
        columns, data = self.cmd.take_action(parsed_args)

        # ImageManager.create(name=, **)
        self.client.create_image.assert_called_with(
            name=self.new_image.name,
            allow_duplicates=True,
            container_format='ovf',
            disk_format='ami',
            min_disk=10,
            min_ram=4,
            owner_id=self.project.id,
            is_protected=self.new_image.is_protected,
            visibility=self.new_image.visibility,
        )

        self.assertEqual(
            self.expected_columns,
            columns)
        self.assertCountEqual(
            self.expected_data,
            data)

    def test_image_create_with_unexist_project(self):
        self.project_mock.get.side_effect = exceptions.NotFound(None)
        self.project_mock.find.side_effect = exceptions.NotFound(None)

        arglist = [
            '--container-format', 'ovf',
            '--disk-format', 'ami',
            '--min-disk', '10',
            '--min-ram', '4',
            '--protected',
            '--private',
            '--project', 'unexist_owner',
            'graven',
        ]
        verifylist = [
            ('container_format', 'ovf'),
            ('disk_format', 'ami'),
            ('min_disk', 10),
            ('min_ram', 4),
            ('protected', True),
            ('unprotected', False),
            ('public', False),
            ('private', True),
            ('project', 'unexist_owner'),
            ('name', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        self.assertRaises(
            exceptions.CommandError,
            self.cmd.take_action,
            parsed_args,
        )

    def test_image_create_file(self):
        imagefile = tempfile.NamedTemporaryFile(delete=False)
        imagefile.write(b'\0')
        imagefile.close()

        arglist = [
            '--file', imagefile.name,
            ('--unprotected'
                if not self.new_image.is_protected else '--protected'),
            ('--public'
                if self.new_image.visibility == 'public' else '--private'),
            '--property', 'Alpha=1',
            '--property', 'Beta=2',
            '--tag', self.new_image.tags[0],
            '--tag', self.new_image.tags[1],
            self.new_image.name,
        ]
        verifylist = [
            ('file', imagefile.name),
            ('protected', self.new_image.is_protected),
            ('unprotected', not self.new_image.is_protected),
            ('public', self.new_image.visibility == 'public'),
            ('private', self.new_image.visibility == 'private'),
            ('properties', {'Alpha': '1', 'Beta': '2'}),
            ('tags', self.new_image.tags),
            ('name', self.new_image.name),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class ShowOne in cliff, abstract method take_action()
        # returns a two-part tuple with a tuple of column names and a tuple of
        # data to be shown.
        columns, data = self.cmd.take_action(parsed_args)

        # ImageManager.create(name=, **)
        self.client.create_image.assert_called_with(
            name=self.new_image.name,
            allow_duplicates=True,
            container_format=image.DEFAULT_CONTAINER_FORMAT,
            disk_format=image.DEFAULT_DISK_FORMAT,
            is_protected=self.new_image.is_protected,
            visibility=self.new_image.visibility,
            Alpha='1',
            Beta='2',
            tags=self.new_image.tags,
            filename=imagefile.name,
        )

        self.assertEqual(
            self.expected_columns,
            columns)
        self.assertCountEqual(
            self.expected_data,
            data)

    def test_image_create_dead_options(self):

        arglist = [
            '--store', 'somewhere',
            self.new_image.name,
        ]
        verifylist = [
            ('name', self.new_image.name),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        self.assertRaises(
            exceptions.CommandError,
            self.cmd.take_action, parsed_args)

    @mock.patch('sys.stdin', side_effect=[None])
    def test_image_create_import(self, raw_input):

        arglist = [
            '--import',
            self.new_image.name,
        ]
        verifylist = [
            ('name', self.new_image.name),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)

        # ImageManager.create(name=, **)
        self.client.create_image.assert_called_with(
            name=self.new_image.name,
            allow_duplicates=True,
            container_format=image.DEFAULT_CONTAINER_FORMAT,
            disk_format=image.DEFAULT_DISK_FORMAT,
            use_import=True
        )


class TestAddProjectToImage(TestImage):

    project = identity_fakes.FakeProject.create_one_project()
    domain = identity_fakes.FakeDomain.create_one_domain()
    _image = image_fakes.create_one_image()
    new_member = image_fakes.create_one_image_member(
        attrs={'image_id': _image.id,
               'member_id': project.id}
    )

    columns = (
        'created_at',
        'image_id',
        'member_id',
        'schema',
        'status',
        'updated_at'
    )

    datalist = (
        new_member.created_at,
        _image.id,
        new_member.member_id,
        new_member.schema,
        new_member.status,
        new_member.updated_at
    )

    def setUp(self):
        super(TestAddProjectToImage, self).setUp()

        # This is the return value for utils.find_resource()
        self.client.find_image.return_value = self._image

        # Update the image_id in the MEMBER dict
        self.client.add_member.return_value = self.new_member
        self.project_mock.get.return_value = self.project
        self.domain_mock.get.return_value = self.domain
        # Get the command object to test
        self.cmd = image.AddProjectToImage(self.app, None)

    def test_add_project_to_image_no_option(self):
        arglist = [
            self._image.id,
            self.project.id,
        ]
        verifylist = [
            ('image', self._image.id),
            ('project', self.project.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class ShowOne in cliff, abstract method take_action()
        # returns a two-part tuple with a tuple of column names and a tuple of
        # data to be shown.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.add_member.assert_called_with(
            image=self._image.id,
            member_id=self.project.id
        )

        self.assertEqual(self.columns, columns)
        self.assertEqual(self.datalist, data)

    def test_add_project_to_image_with_option(self):
        arglist = [
            self._image.id,
            self.project.id,
            '--project-domain', self.domain.id,
        ]
        verifylist = [
            ('image', self._image.id),
            ('project', self.project.id),
            ('project_domain', self.domain.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class ShowOne in cliff, abstract method take_action()
        # returns a two-part tuple with a tuple of column names and a tuple of
        # data to be shown.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.add_member.assert_called_with(
            image=self._image.id,
            member_id=self.project.id
        )

        self.assertEqual(self.columns, columns)
        self.assertEqual(self.datalist, data)


class TestImageDelete(TestImage):

    def setUp(self):
        super(TestImageDelete, self).setUp()

        self.client.delete_image.return_value = None

        # Get the command object to test
        self.cmd = image.DeleteImage(self.app, None)

    def test_image_delete_no_options(self):
        images = self.setup_images_mock(count=1)

        arglist = [
            images[0].id,
        ]
        verifylist = [
            ('images', [images[0].id]),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        self.client.find_image.side_effect = images

        result = self.cmd.take_action(parsed_args)

        self.client.delete_image.assert_called_with(images[0].id)
        self.assertIsNone(result)

    def test_image_delete_multi_images(self):
        images = self.setup_images_mock(count=3)

        arglist = [i.id for i in images]
        verifylist = [
            ('images', arglist),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        self.client.find_image.side_effect = images

        result = self.cmd.take_action(parsed_args)

        calls = [mock.call(i.id) for i in images]
        self.client.delete_image.assert_has_calls(calls)
        self.assertIsNone(result)

    def test_image_delete_multi_images_exception(self):

        images = image_fakes.create_images(count=2)
        arglist = [
            images[0].id,
            images[1].id,
            'x-y-x',
        ]
        verifylist = [
            ('images', arglist)
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # Fake exception in utils.find_resource()
        # In image v2, we use utils.find_resource() to find a network.
        # It calls get() several times, but find() only one time. So we
        # choose to fake get() always raise exception, then pass through.
        # And fake find() to find the real network or not.
        ret_find = [
            images[0],
            images[1],
            sdk_exceptions.ResourceNotFound()
        ]

        self.client.find_image.side_effect = ret_find

        self.assertRaises(exceptions.CommandError, self.cmd.take_action,
                          parsed_args)
        calls = [mock.call(i.id) for i in images]
        self.client.delete_image.assert_has_calls(calls)


class TestImageList(TestImage):

    _image = image_fakes.create_one_image()

    columns = (
        'ID',
        'Name',
        'Status',
    )

    datalist = (
        _image.id,
        _image.name,
        None,
    ),

    def setUp(self):
        super(TestImageList, self).setUp()

        self.client.images.side_effect = [[self._image], []]

        # Get the command object to test
        self.cmd = image.ListImage(self.app, None)

    def test_image_list_no_options(self):
        arglist = []
        verifylist = [
            ('public', False),
            ('private', False),
            ('community', False),
            ('shared', False),
            ('long', False),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            # marker=self._image.id,
        )

        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.datalist, tuple(data))

    def test_image_list_public_option(self):
        arglist = [
            '--public',
        ]
        verifylist = [
            ('public', True),
            ('private', False),
            ('community', False),
            ('shared', False),
            ('long', False),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            visibility='public',
        )

        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.datalist, tuple(data))

    def test_image_list_private_option(self):
        arglist = [
            '--private',
        ]
        verifylist = [
            ('public', False),
            ('private', True),
            ('community', False),
            ('shared', False),
            ('long', False),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            visibility='private',
        )

        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.datalist, tuple(data))

    def test_image_list_community_option(self):
        arglist = [
            '--community',
        ]
        verifylist = [
            ('public', False),
            ('private', False),
            ('community', True),
            ('shared', False),
            ('long', False),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            visibility='community',
        )

        self.assertEqual(self.columns, columns)
        self.assertEqual(self.datalist, tuple(data))

    def test_image_list_shared_option(self):
        arglist = [
            '--shared',
        ]
        verifylist = [
            ('public', False),
            ('private', False),
            ('community', False),
            ('shared', True),
            ('long', False),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            visibility='shared',
        )

        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.datalist, tuple(data))

    def test_image_list_shared_member_status_option(self):
        arglist = [
            '--shared',
            '--member-status', 'all'
        ]
        verifylist = [
            ('public', False),
            ('private', False),
            ('community', False),
            ('shared', True),
            ('long', False),
            ('member_status', 'all')
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            visibility='shared',
            member_status='all',
        )

        self.assertEqual(self.columns, columns)
        self.assertEqual(self.datalist, tuple(data))

    def test_image_list_shared_member_status_lower(self):
        arglist = [
            '--shared',
            '--member-status', 'ALl'
        ]
        verifylist = [
            ('public', False),
            ('private', False),
            ('community', False),
            ('shared', True),
            ('long', False),
            ('member_status', 'all')
        ]
        self.check_parser(self.cmd, arglist, verifylist)

    def test_image_list_long_option(self):
        arglist = [
            '--long',
        ]
        verifylist = [
            ('long', True),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
        )

        collist = (
            'ID',
            'Name',
            'Disk Format',
            'Container Format',
            'Size',
            'Checksum',
            'Status',
            'Visibility',
            'Protected',
            'Project',
            'Tags',
        )

        self.assertEqual(collist, columns)
        datalist = ((
            self._image.id,
            self._image.name,
            None,
            None,
            None,
            None,
            None,
            self._image.visibility,
            self._image.is_protected,
            self._image.owner_id,
            format_columns.ListColumn(self._image.tags),
        ), )
        self.assertCountEqual(datalist, tuple(data))

    @mock.patch('osc_lib.api.utils.simple_filter')
    def test_image_list_property_option(self, sf_mock):
        sf_mock.return_value = [copy.deepcopy(self._image)]

        arglist = [
            '--property', 'a=1',
        ]
        verifylist = [
            ('property', {'a': '1'}),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
        )
        sf_mock.assert_called_with(
            [self._image],
            attr='a',
            value='1',
            property_field='properties',
        )

        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.datalist, tuple(data))

    @mock.patch('osc_lib.utils.sort_items')
    def test_image_list_sort_option(self, si_mock):
        si_mock.return_value = [copy.deepcopy(self._image)]

        arglist = ['--sort', 'name:asc']
        verifylist = [('sort', 'name:asc')]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class Lister in cliff, abstract method take_action()
        # returns a tuple containing the column names and an iterable
        # containing the data to be listed.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
        )
        si_mock.assert_called_with(
            [self._image],
            'name:asc',
            str,
        )
        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.datalist, tuple(data))

    def test_image_list_limit_option(self):
        ret_limit = 1
        arglist = [
            '--limit', str(ret_limit),
        ]
        verifylist = [
            ('limit', ret_limit),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            limit=ret_limit,
            paginated=False
            # marker=None
        )

        self.assertEqual(self.columns, columns)
        self.assertEqual(ret_limit, len(tuple(data)))

    def test_image_list_project_option(self):
        self.client.find_image = mock.Mock(return_value=self._image)
        arglist = [
            '--project', 'nova',
        ]
        verifylist = [
            ('project', 'nova'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)

        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.datalist, tuple(data))

    @mock.patch('osc_lib.utils.find_resource')
    def test_image_list_marker_option(self, fr_mock):
        self.client.find_image = mock.Mock(return_value=self._image)

        arglist = [
            '--marker', 'graven',
        ]
        verifylist = [
            ('marker', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            marker=self._image.id,
        )

        self.client.find_image.assert_called_with('graven')

    def test_image_list_name_option(self):
        arglist = [
            '--name', 'abc',
        ]
        verifylist = [
            ('name', 'abc'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            name='abc',
            # marker=self._image.id
        )

    def test_image_list_status_option(self):
        arglist = [
            '--status', 'active',
        ]
        verifylist = [
            ('status', 'active'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            status='active'
        )

    def test_image_list_hidden_option(self):
        arglist = [
            '--hidden',
        ]
        verifylist = [
            ('hidden', True),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            is_hidden=True
        )

    def test_image_list_tag_option(self):
        arglist = [
            '--tag', 'abc',
        ]
        verifylist = [
            ('tag', 'abc'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)
        self.client.images.assert_called_with(
            tag='abc'
        )


class TestListImageProjects(TestImage):

    project = identity_fakes.FakeProject.create_one_project()
    _image = image_fakes.create_one_image()
    member = image_fakes.create_one_image_member(
        attrs={'image_id': _image.id,
               'member_id': project.id}
    )

    columns = (
        "Image ID",
        "Member ID",
        "Status"
    )

    datalist = [(
        _image.id,
        member.member_id,
        member.status,
    )]

    def setUp(self):
        super(TestListImageProjects, self).setUp()

        self.client.find_image.return_value = self._image
        self.client.members.return_value = [self.member]

        self.cmd = image.ListImageProjects(self.app, None)

    def test_image_member_list(self):
        arglist = [
            self._image.id
        ]
        verifylist = [
            ('image', self._image.id)
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        columns, data = self.cmd.take_action(parsed_args)

        self.client.members.assert_called_with(image=self._image.id)

        self.assertEqual(self.columns, columns)
        self.assertEqual(self.datalist, list(data))


class TestRemoveProjectImage(TestImage):

    project = identity_fakes.FakeProject.create_one_project()
    domain = identity_fakes.FakeDomain.create_one_domain()

    def setUp(self):
        super(TestRemoveProjectImage, self).setUp()

        self._image = image_fakes.create_one_image()
        # This is the return value for utils.find_resource()
        self.client.find_image.return_value = self._image

        self.project_mock.get.return_value = self.project
        self.domain_mock.get.return_value = self.domain
        self.client.remove_member.return_value = None
        # Get the command object to test
        self.cmd = image.RemoveProjectImage(self.app, None)

    def test_remove_project_image_no_options(self):
        arglist = [
            self._image.id,
            self.project.id,
        ]
        verifylist = [
            ('image', self._image.id),
            ('project', self.project.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        self.client.find_image.assert_called_with(
            self._image.id,
            ignore_missing=False)

        self.client.remove_member.assert_called_with(
            member=self.project.id,
            image=self._image.id,
        )
        self.assertIsNone(result)

    def test_remove_project_image_with_options(self):
        arglist = [
            self._image.id,
            self.project.id,
            '--project-domain', self.domain.id,
        ]
        verifylist = [
            ('image', self._image.id),
            ('project', self.project.id),
            ('project_domain', self.domain.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        self.client.remove_member.assert_called_with(
            member=self.project.id,
            image=self._image.id,
        )
        self.assertIsNone(result)


class TestImageSet(TestImage):

    project = identity_fakes.FakeProject.create_one_project()
    domain = identity_fakes.FakeDomain.create_one_domain()
    _image = image_fakes.create_one_image({'tags': []})

    def setUp(self):
        super(TestImageSet, self).setUp()

        self.project_mock.get.return_value = self.project

        self.domain_mock.get.return_value = self.domain

        self.client.find_image.return_value = self._image

        self.app.client_manager.auth_ref = mock.Mock(
            project_id=self.project.id,
        )

        # Get the command object to test
        self.cmd = image.SetImage(self.app, None)

    def test_image_set_no_options(self):
        arglist = [
            '0f41529e-7c12-4de8-be2d-181abb825b3c',
        ]
        verifylist = [
            ('image', '0f41529e-7c12-4de8-be2d-181abb825b3c')
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        self.assertIsNone(result)
        # we'll have called this but not set anything
        self.app.client_manager.image.update_image.called_once_with(
            self._image.id,
        )

    def test_image_set_membership_option_accept(self):
        membership = image_fakes.create_one_image_member(
            attrs={'image_id': '0f41529e-7c12-4de8-be2d-181abb825b3c',
                   'member_id': self.project.id}
        )
        self.client.update_member.return_value = membership

        arglist = [
            '--accept',
            self._image.id,
        ]
        verifylist = [
            ('membership', 'accepted'),
            ('image', self._image.id)
        ]

        parsed_args = self.check_parser(self.cmd, arglist, verifylist)
        self.cmd.take_action(parsed_args)

        self.client.update_member.assert_called_once_with(
            image=self._image.id,
            member=self.app.client_manager.auth_ref.project_id,
            status='accepted',
        )

        # Assert that the 'update image" route is also called, in addition to
        # the 'update membership' route.
        self.client.update_image.assert_called_with(self._image.id)

    def test_image_set_membership_option_reject(self):
        membership = image_fakes.create_one_image_member(
            attrs={'image_id': '0f41529e-7c12-4de8-be2d-181abb825b3c',
                   'member_id': self.project.id}
        )
        self.client.update_member.return_value = membership

        arglist = [
            '--reject',
            '0f41529e-7c12-4de8-be2d-181abb825b3c',
        ]
        verifylist = [
            ('membership', 'rejected'),
            ('image', '0f41529e-7c12-4de8-be2d-181abb825b3c')
        ]

        parsed_args = self.check_parser(self.cmd, arglist, verifylist)
        self.cmd.take_action(parsed_args)

        self.client.update_member.assert_called_once_with(
            image=self._image.id,
            member=self.app.client_manager.auth_ref.project_id,
            status='rejected',
        )

        # Assert that the 'update image" route is also called, in addition to
        # the 'update membership' route.
        self.client.update_image.assert_called_with(self._image.id)

    def test_image_set_membership_option_pending(self):
        membership = image_fakes.create_one_image_member(
            attrs={'image_id': '0f41529e-7c12-4de8-be2d-181abb825b3c',
                   'member_id': self.project.id}
        )
        self.client.update_member.return_value = membership

        arglist = [
            '--pending',
            '0f41529e-7c12-4de8-be2d-181abb825b3c',
        ]
        verifylist = [
            ('membership', 'pending'),
            ('image', '0f41529e-7c12-4de8-be2d-181abb825b3c')
        ]

        parsed_args = self.check_parser(self.cmd, arglist, verifylist)
        self.cmd.take_action(parsed_args)

        self.client.update_member.assert_called_once_with(
            image=self._image.id,
            member=self.app.client_manager.auth_ref.project_id,
            status='pending',
        )

        # Assert that the 'update image" route is also called, in addition to
        # the 'update membership' route.
        self.client.update_image.assert_called_with(self._image.id)

    def test_image_set_options(self):
        arglist = [
            '--name', 'new-name',
            '--min-disk', '2',
            '--min-ram', '4',
            '--container-format', 'ovf',
            '--disk-format', 'vmdk',
            '--project', self.project.name,
            '--project-domain', self.domain.id,
            self._image.id,
        ]
        verifylist = [
            ('name', 'new-name'),
            ('min_disk', 2),
            ('min_ram', 4),
            ('container_format', 'ovf'),
            ('disk_format', 'vmdk'),
            ('project', self.project.name),
            ('project_domain', self.domain.id),
            ('image', self._image.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'name': 'new-name',
            'owner_id': self.project.id,
            'min_disk': 2,
            'min_ram': 4,
            'container_format': 'ovf',
            'disk_format': 'vmdk',
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id, **kwargs)
        self.assertIsNone(result)

    def test_image_set_with_unexist_project(self):
        self.project_mock.get.side_effect = exceptions.NotFound(None)
        self.project_mock.find.side_effect = exceptions.NotFound(None)

        arglist = [
            '--project', 'unexist_owner',
            '0f41529e-7c12-4de8-be2d-181abb825b3c',
        ]
        verifylist = [
            ('project', 'unexist_owner'),
            ('image', '0f41529e-7c12-4de8-be2d-181abb825b3c'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        self.assertRaises(
            exceptions.CommandError,
            self.cmd.take_action, parsed_args)

    def test_image_set_bools1(self):
        arglist = [
            '--protected',
            '--private',
            'graven',
        ]
        verifylist = [
            ('protected', True),
            ('unprotected', False),
            ('public', False),
            ('private', True),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'is_protected': True,
            'visibility': 'private',
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_bools2(self):
        arglist = [
            '--unprotected',
            '--public',
            'graven',
        ]
        verifylist = [
            ('protected', False),
            ('unprotected', True),
            ('public', True),
            ('private', False),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'is_protected': False,
            'visibility': 'public',
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_properties(self):
        arglist = [
            '--property', 'Alpha=1',
            '--property', 'Beta=2',
            'graven',
        ]
        verifylist = [
            ('properties', {'Alpha': '1', 'Beta': '2'}),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'Alpha': '1',
            'Beta': '2',
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_fake_properties(self):
        arglist = [
            '--architecture', 'z80',
            '--instance-id', '12345',
            '--kernel-id', '67890',
            '--os-distro', 'cpm',
            '--os-version', '2.2H',
            '--ramdisk-id', 'xyzpdq',
            'graven',
        ]
        verifylist = [
            ('architecture', 'z80'),
            ('instance_id', '12345'),
            ('kernel_id', '67890'),
            ('os_distro', 'cpm'),
            ('os_version', '2.2H'),
            ('ramdisk_id', 'xyzpdq'),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'architecture': 'z80',
            'instance_id': '12345',
            'kernel_id': '67890',
            'os_distro': 'cpm',
            'os_version': '2.2H',
            'ramdisk_id': 'xyzpdq',
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_tag(self):
        arglist = [
            '--tag', 'test-tag',
            'graven',
        ]
        verifylist = [
            ('tags', ['test-tag']),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'tags': ['test-tag'],
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_activate(self):
        arglist = [
            '--tag', 'test-tag',
            '--activate',
            'graven',
        ]
        verifylist = [
            ('tags', ['test-tag']),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'tags': ['test-tag'],
        }

        self.client.reactivate_image.assert_called_with(
            self._image.id,
        )
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_deactivate(self):
        arglist = [
            '--tag', 'test-tag',
            '--deactivate',
            'graven',
        ]
        verifylist = [
            ('tags', ['test-tag']),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'tags': ['test-tag'],
        }

        self.client.deactivate_image.assert_called_with(
            self._image.id,
        )
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_tag_merge(self):
        old_image = self._image
        old_image['tags'] = ['old1', 'new2']
        self.client.find_image.return_value = old_image
        arglist = [
            '--tag', 'test-tag',
            'graven',
        ]
        verifylist = [
            ('tags', ['test-tag']),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'tags': ['old1', 'new2', 'test-tag'],
        }
        # ImageManager.update(image, **kwargs)
        a, k = self.client.update_image.call_args
        self.assertEqual(self._image.id, a[0])
        self.assertIn('tags', k)
        self.assertEqual(set(kwargs['tags']), set(k['tags']))
        self.assertIsNone(result)

    def test_image_set_tag_merge_dupe(self):
        old_image = self._image
        old_image['tags'] = ['old1', 'new2']
        self.client.find_image.return_value = old_image
        arglist = [
            '--tag', 'old1',
            'graven',
        ]
        verifylist = [
            ('tags', ['old1']),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'tags': ['new2', 'old1'],
        }
        # ImageManager.update(image, **kwargs)
        a, k = self.client.update_image.call_args
        self.assertEqual(self._image.id, a[0])
        self.assertIn('tags', k)
        self.assertEqual(set(kwargs['tags']), set(k['tags']))
        self.assertIsNone(result)

    def test_image_set_dead_options(self):

        arglist = [
            '--visibility', '1-mile',
            'graven',
        ]
        verifylist = [
            ('visibility', '1-mile'),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        self.assertRaises(
            exceptions.CommandError,
            self.cmd.take_action, parsed_args)

    def test_image_set_numeric_options_to_zero(self):
        arglist = [
            '--min-disk', '0',
            '--min-ram', '0',
            'graven',
        ]
        verifylist = [
            ('min_disk', 0),
            ('min_ram', 0),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'min_disk': 0,
            'min_ram': 0,
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_hidden(self):
        arglist = [
            '--hidden',
            '--public',
            'graven',
        ]
        verifylist = [
            ('hidden', True),
            ('public', True),
            ('private', False),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'is_hidden': True,
            'visibility': 'public',
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)

    def test_image_set_unhidden(self):
        arglist = [
            '--unhidden',
            '--public',
            'graven',
        ]
        verifylist = [
            ('hidden', False),
            ('public', True),
            ('private', False),
            ('image', 'graven'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        kwargs = {
            'is_hidden': False,
            'visibility': 'public',
        }
        # ImageManager.update(image, **kwargs)
        self.client.update_image.assert_called_with(
            self._image.id,
            **kwargs
        )
        self.assertIsNone(result)


class TestImageShow(TestImage):

    new_image = image_fakes.create_one_image(
        attrs={'size': 1000})

    _data = image_fakes.create_one_image()

    columns = (
        'id', 'name', 'owner', 'protected', 'tags', 'visibility'
    )

    data = (
        _data.id,
        _data.name,
        _data.owner_id,
        _data.is_protected,
        format_columns.ListColumn(_data.tags),
        _data.visibility
    )

    def setUp(self):
        super(TestImageShow, self).setUp()

        self.client.find_image = mock.Mock(return_value=self._data)

        # Get the command object to test
        self.cmd = image.ShowImage(self.app, None)

    def test_image_show(self):
        arglist = [
            '0f41529e-7c12-4de8-be2d-181abb825b3c',
        ]
        verifylist = [
            ('image', '0f41529e-7c12-4de8-be2d-181abb825b3c'),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class ShowOne in cliff, abstract method take_action()
        # returns a two-part tuple with a tuple of column names and a tuple of
        # data to be shown.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.find_image.assert_called_with(
            '0f41529e-7c12-4de8-be2d-181abb825b3c',
            ignore_missing=False
        )

        self.assertEqual(self.columns, columns)
        self.assertCountEqual(self.data, data)

    def test_image_show_human_readable(self):
        self.client.find_image.return_value = self.new_image
        arglist = [
            '--human-readable',
            self.new_image.id,
        ]
        verifylist = [
            ('human_readable', True),
            ('image', self.new_image.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        # In base command class ShowOne in cliff, abstract method take_action()
        # returns a two-part tuple with a tuple of column names and a tuple of
        # data to be shown.
        columns, data = self.cmd.take_action(parsed_args)
        self.client.find_image.assert_called_with(
            self.new_image.id,
            ignore_missing=False
        )

        size_index = columns.index('size')
        self.assertEqual(data[size_index], '1K')


class TestImageUnset(TestImage):

    def setUp(self):
        super(TestImageUnset, self).setUp()

        attrs = {}
        attrs['tags'] = ['test']
        attrs['hw_rng_model'] = 'virtio'
        attrs['prop'] = 'test'
        attrs['prop2'] = 'fake'
        self.image = image_fakes.create_one_image(attrs)

        self.client.find_image.return_value = self.image
        self.client.remove_tag.return_value = self.image
        self.client.update_image.return_value = self.image

        # Get the command object to test
        self.cmd = image.UnsetImage(self.app, None)

    def test_image_unset_no_options(self):
        arglist = [
            '0f41529e-7c12-4de8-be2d-181abb825b3c',
        ]
        verifylist = [
            ('image', '0f41529e-7c12-4de8-be2d-181abb825b3c')
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        result = self.cmd.take_action(parsed_args)

        self.assertIsNone(result)

    def test_image_unset_tag_option(self):

        arglist = [
            '--tag', 'test',
            self.image.id,
        ]

        verifylist = [
            ('tags', ['test']),
            ('image', self.image.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)
        result = self.cmd.take_action(parsed_args)

        self.client.remove_tag.assert_called_with(
            self.image.id, 'test'
        )
        self.assertIsNone(result)

    def test_image_unset_property_option(self):

        arglist = [
            '--property', 'hw_rng_model',
            '--property', 'prop',
            self.image.id,
        ]

        verifylist = [
            ('properties', ['hw_rng_model', 'prop']),
            ('image', self.image.id)
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)
        result = self.cmd.take_action(parsed_args)

        self.client.update_image.assert_called_with(
            self.image, properties={'prop2': 'fake'})

        self.assertIsNone(result)

    def test_image_unset_mixed_option(self):

        arglist = [
            '--tag', 'test',
            '--property', 'hw_rng_model',
            '--property', 'prop',
            self.image.id,
        ]

        verifylist = [
            ('tags', ['test']),
            ('properties', ['hw_rng_model', 'prop']),
            ('image', self.image.id)
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)
        result = self.cmd.take_action(parsed_args)

        self.client.update_image.assert_called_with(
            self.image, properties={'prop2': 'fake'})

        self.client.remove_tag.assert_called_with(
            self.image.id, 'test'
        )
        self.assertIsNone(result)


class TestImageSave(TestImage):

    image = image_fakes.create_one_image({})

    def setUp(self):
        super(TestImageSave, self).setUp()

        self.client.find_image.return_value = self.image
        self.client.download_image.return_value = self.image

        # Get the command object to test
        self.cmd = image.SaveImage(self.app, None)

    def test_save_data(self):

        arglist = ['--file', '/path/to/file', self.image.id]

        verifylist = [
            ('file', '/path/to/file'),
            ('image', self.image.id),
        ]
        parsed_args = self.check_parser(self.cmd, arglist, verifylist)

        self.cmd.take_action(parsed_args)

        self.client.download_image.assert_called_once_with(
            self.image.id,
            stream=True,
            output='/path/to/file')


class TestImageGetData(TestImage):

    def setUp(self):
        super(TestImageGetData, self).setUp()
        self.args = mock.Mock()

    def test_get_data_file_file(self):
        (fd, fname) = tempfile.mkstemp(prefix='osc_test_image')
        self.args.file = fname

        (test_fd, test_name) = image.get_data_file(self.args)

        self.assertEqual(fname, test_name)
        test_fd.close()

        os.unlink(fname)

    def test_get_data_file_2(self):

        self.args.file = None

        f = io.BytesIO(b"some initial binary data: \x00\x01")

        with mock.patch('sys.stdin') as stdin:
            stdin.return_value = f
            stdin.isatty.return_value = False
            stdin.buffer = f

            (test_fd, test_name) = image.get_data_file(self.args)

            # Ensure data written to temp file is correct
            self.assertEqual(f, test_fd)
            self.assertIsNone(test_name)

    def test_get_data_file_3(self):

        self.args.file = None

        f = io.BytesIO(b"some initial binary data: \x00\x01")

        with mock.patch('sys.stdin') as stdin:
            # There is stdin, but interactive
            stdin.return_value = f

            (test_fd, test_fname) = image.get_data_file(self.args)

            self.assertIsNone(test_fd)
            self.assertIsNone(test_fname)

from __future__ import print_function

import os
import re
import yaml


base_dirs = {
    'build': 'scaffold.BuildDir',
    'build/test-framework': 'scaffold.BuildTestDir',
    'deploy': 'scaffold.DeployDir',
    'deploy/crds': 'scaffold.CrdsDir',
    'roles/{{.Resource.LowerKind}}': 'RolesDir, {short_name}.Resource.LowerKind',
    'molecule': 'MoleculeDir',
    'molecule/cluster': 'MoleculeClusterDir',
    'molecule/test-local': 'MoleculeTestLocalDir',
    'molecule/default': 'MoleculeDefaultDir',
}


class Formatter(object):

    dir_constants = {
        'MoleculeDir': '"molecule"',
        'MoleculeClusterDir': 'filepath.Join(MoleculeDir, "cluster")',
        'MoleculeTestLocalDir': 'filepath.Join(MoleculeDir, "test-local")',
        'MoleculeDefaultDir': 'filepath.Join(MoleculeDir, "default")',
    }

    __name = None
    __filename = None
    __vars_decl = None
    __base_dir = None
    __raw_base_dir = None
    __vars_value = None
    __file_content = None

    def __init__(self, root, input_file):
        self.constants_map = {}
        self.input_root = root
        self.root = self._remove_top_dir(root)
        self.input_file = input_file
        self.filename_vars = self.extract_vars(os.path.join(root, input_file))
        with open(os.path.join(root, input_file)) as f:
            self.input_content = f.read()
        self.content_vars = self.extract_vars(self.input_content)

    def _remove_top_dir(self, path):
        if '/' in path:
            return path.split('/', 1)[1]
        return ''

    @property
    def name(self):
        if self.__name is not None:
            return self.__name
        if '.' in self.input_file:
            name = camel_case(''.join(filter(None, self.input_file.split('.')[0:-1])).capitalize())
        else:
            name = camel_case(self.input_file)
        name = camel_case(self.raw_base_dir) + name
        self.__name = re.sub(r'{.*}', '', name)
        return self.__name

    def process_vars(self, s, names):
        if names:
            for var in names:
                if not conversions.get(var):
                    update_conversions(var, raw_input('{}: '.format(var)))
                s = s.replace(var, conversions[var])
        return s

    @property
    def raw_base_dir(self):
        if self.__raw_base_dir is not None:
            return self.__raw_base_dir

        base_dir = self.root
        base_dir = self.process_vars(base_dir, self.filename_vars)
        self.__raw_base_dir = base_dir
        return self.__raw_base_dir

    @property
    def base_dir(self):
        if self.__base_dir is not None:
            return self.__base_dir

        base_dir = self.raw_base_dir
        matches = sorted([(k, v) for k, v in base_dirs.items() if base_dir.startswith(k.strip('/'))], key=lambda x: 0 - len(x[0]))
        if matches:
            base_dir = matches[0][1]
            base_dir = base_dir.replace(matches[0][0], '')
        elif base_dir:
            __import__('pdb').set_trace()
        self.__base_dir = base_dir
        return self.__base_dir

    @property
    def filename(self):
        if self.__filename is not None:
            return self.__filename
        filename = self.process_vars(self.input_file, self.filename_vars)
        self.constants_map[camel_case(self.name) + 'File'] = filename
        self.__filename = camel_case(self.name + 'File')

        return self.__filename

    @property
    def file_content(self):
        if self.__file_content is not None:
            return self.__file_content
        self.__file_content = self.process_vars(self.input_content, self.content_vars).replace('{', '{{').replace('}', '}}')
        return self.__file_content

    def parse_vars(self):
        var_re = r'\.([A-Z][a-z]*\.?.*?)[ }]+'
        matches = self.extract_vars(self.file_content)
        if matches:
            go_vars = {y.split('.')[0] for x in matches for y in re.findall(var_re, x) if y != 'ProjectName'}
            for var in list(go_vars):
                if not conversions.get(var):
                    update_conversions(var, raw_input('type of {}?: '.format(var)))
            if go_vars:
                longest = max(map(len, go_vars))
                vars_decl_tmpl = '\t{} {}'
                self.__vars_decl = '\n'.join([
                    vars_decl_tmpl.format(item.ljust(longest), conversions.get(item))
                    for item in go_vars
                ])
                vars_value_tmpl = '\t{} = {}'
                vars_value = ['{short_name}.' + var for var in go_vars]
                for var in vars_value:
                    if not conversions.get(var):
                        update_conversions(var, raw_input('{} = ?: '.format(var)))
                self.__vars_value = '\n'.join([
                    vars_value_tmpl.format(item, conversions.get(item))
                    for item in vars_value if conversions.get(item) != "IGNORE"
                ])
                return
        self.__vars_decl = ""
        self.__vars_value = ""

    @property
    def vars_decl(self):
        if self.__vars_decl is not None:
            return self.__vars_decl
        self.parse_vars()
        return self.__vars_decl

    @property
    def vars_value(self):
        if self.__vars_value is not None:
            return self.__vars_value
        self.parse_vars()
        return self.__vars_value

    @property
    def short_name(self):
        return self.name[0].lower()

    @property
    def private_name(self):
        return self.name[0].lower() + ''.join(self.name[1:])

    @property
    def source_filename(self):
        return snake_case(self.name) + '.go'

    @property
    def constants(self):
        ret = ""
        for k, v in self.constants_map.items():
            ret = ret + 'const {} = "{}"\n'.format(k, v)
        return ret

    @property
    def filepath_string(self):
        if self.raw_base_dir:
            return 'filepath.Join({base_dir}, {filename})'.format(base_dir=self.base_dir, filename=self.filename)
        return '{filename}'.format(filename=self.filename)

    def format(self):
        format_args = dict(
            name=self.name,
            vars_decl=self.vars_decl,
            vars_value=self.vars_value,
            short_name=self.short_name,
            private_name=self.private_name,
            filepath_string=self.filepath_string,
            base_dir=self.base_dir,
            filename=self.filename,
            file_content=self.file_content,
            constants=self.constants,
        )
        return TMPL.format(**format_args).format(**format_args)

    def extract_vars(self, text):
        return re.findall(r'{[{%].*?[}%]}', text)


TMPL = """// Copyright 2018 The Operator-SDK Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package ansible

{constants}
type {name} struct {{{{
\tinput.Input
{vars_decl}
}}}}

// GetInput - gets the input
func ({short_name} *{name}) GetInput() (input.Input, error) {{{{
\tif {short_name}.Path == "" {{{{
\t\t{short_name}.Path = {filepath_string}
\t}}}}
\t{short_name}.TemplateBody = {private_name}AnsibleTmpl
{vars_value}
\treturn {short_name}.Input, nil
}}}}

const {private_name}AnsibleTmpl = `{file_content}`
"""

CONSTANTS_TMPL = """// Copyright 2018 The Operator-SDK Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package ansible

import (
    "path/filepath"
)

const (
{constants}
)
"""

conversions = {}
if os.path.exists('.cache'):
    with open('.cache') as f:
        conversions = yaml.load(f.read())


def update_conversions(key, value):
    conversions[key] = value
    with open('.cache', 'w') as f:
        f.write(yaml.dump(conversions, default_flow_style=False))


def capitalize(s):
    if not s:
        return s
    return s[0].upper() + (''.join(s[1:]) if len(s) > 1 else '')


def snake_case(s):
    if not s:
        return s
    return '_'.join(filter(lambda x: x, re.findall(r'([A-Z]*[a-z]*)', s))).lower()


def camel_case(s):
    new_s = ''.join([capitalize(x) for x in s.split('/')])
    new_s = ''.join([capitalize(x) for x in new_s.split('-')])
    new_s = ''.join([capitalize(x) for x in new_s.split('_')])
    new_s = ''.join([capitalize(x) for x in new_s.split('.')])
    return new_s


def main():
    if not os.path.exists('tmpl'):
        print("No 'tmpl' directory found")
        raise SystemExit(1)
    for root, dirs, files in os.walk('tmpl'):
        for file in files:
            formatter = Formatter(root, file)
            with open(formatter.source_filename, 'w') as f:
                f.write(formatter.format())

    fmt_line = '\t{} = {}'
    lines = []
    constants = Formatter.dir_constants.items()
    longest = max(list(map(lambda x: len(x[0]), constants)))
    for (k, v) in constants:
        lines.append(fmt_line.format(k.ljust(longest), v))
    formatted = '\n'.join(lines)

    with open('constants.go', 'w') as f:
        f.write(CONSTANTS_TMPL.format(constants=formatted))


if __name__ == '__main__':
    main()

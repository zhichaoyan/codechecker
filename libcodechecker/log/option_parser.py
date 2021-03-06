# -------------------------------------------------------------------------
#                     The CodeChecker Infrastructure
#   This file is distributed under the University of Illinois Open Source
#   License. See LICENSE.TXT for details.
# -------------------------------------------------------------------------
"""
An extended lookup table for compiler arguments based on ScanBuild
clang-analyzer.llvm.org/scan-build.html

Used to filter out or change compiler argument not supported by clang
or clang-tidy.

Keys are the option name, value is the number of options to skip.

Possible improvements:
    - modular option handling system configuring possibility from config file.

"""
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
import os
import re
import shlex

from libcodechecker.logger import get_logger

LOG = get_logger('buildlogger')

# Compiler options in the following format
# argument_name: number of parameters sepearated by space.

COMPILE_OPTION_MAP = {
    '-nostdinc': 0,
    '--sysroot': 1,
    '--include': 1,
    '-pedantic': 0,
    '-G': 1
}

# Compiler options which are followed by 1 parameter with or without
# space in between e.g. "-I/include" "-I /include".
# After parsing the parameter will be merged to the compiler option.
COMPILE_OPTION_MAP_MERGED = [
    '^-iquote(.*)$',
    '^-[DIU](.*)$',
    '^-F(.+)$',
    '^-idirafter(.*)$',
    '^-isystem(.*)$',
    '^-imacros(.*)$',
    '^-include(.*)$',
    '^-isysroot(.*)$',
    '^-iprefix(.*)$',
    '^-iwithprefix(.*)$',
    '^-iwithprefixbefore(.*)$'
]


COMPILE_OPTION_MAP_REGEX = {
    '-O([1-3]|s)?$': 0,
    '-std=.*': 0,
    '^-f.*': 0,
    '-m.*': 0,
    '^-Wno-.*': 0,
    '^-m(32|64)$': 0,
    '^--sysroot=': 0,
    '^--gcc-toolchain=': 0
}

# Linker options.

LINKER_OPTION_MAP_REGEX = {
    '^-:L.*$': 0,
    '^-l.*$': 0,
    '^-shared.*$': 0,
    '^-static.*$': 0
}

COMPILER_LINKER_OPTION_MAP = {
    '-Xlinker': 1,
    '-ftrapv-handler': 1,
    '-lobjc': 0,
    '-mios-simulator-version-min': 0,
    '-miphoneos-version-min': 0,
    '-mmacosx-version-min': 0,
    '-no-pie': 0,
    '-nostartfiles': 0,
    '-nostdlib': 0,
    '-pie': 0,
    '-rdynamic': 0,
    '-s': 0,
    '-stdlib': 0,
    '-target': 1,  # This is a clang compiler option!
    '-v': 0,
    '-write-strings': 0
}

LINKER_OPTION_MAP = {
    '-framework': 1,
    '-fobjc-link-runtime': 0
}

LINK_OPTION_MAP_MERGED = [
    '^-[L](.*)$',
]

# Replace gcc/g++ build target options with values
# accepted by clang.

REPLACE_OPTIONS_MAP = {
    '-mips32': ['-target', 'mips', '-mips32'],
    '-mips64': ['-target', 'mips64', '-mips64'],
    '-mpowerpc': ['-target', 'powerpc'],
    '-mpowerpc64': ['-target', 'powerpc64']
}

# Ignored options.

IGNORED_OPTION_MAP = {
    '-MT': 1,
    '-MQ': 1,
    '-MF': 1,
    '-MJ': 1,
    '-MM': 0,
    '-MP': 0,
    '-MD': 0,
    '-MV': 0,
    '-MMD': 0,
    '-save-temps': 0,
    '-install_name': 1,
    '-exported_symbols_list': 1,
    '-current_version': 1,
    '-compatibility_version': 1,
    '-init': 1,
    '-e': 1,
    '-seg1addr': 1,
    '-bundle_loader': 1,
    '-multiply_defined': 1,
    '-sectorder': 3,
    '--param': 1,
    '-u': 1,
    '--serialize-diagnostics': 1,
    # Clang gives different warnings than GCC. Thus if these flags are kept,
    # '-Werror', '-pedantic-errors' the analysis with Clang can fail even
    # if the compilation passes with GCC.
    '-Werror': 0,
    '-pedantic-errors': 0
}

IGNORED_OPTION_MAP_REGEX = {
    '^-g(.+)?$': 0,
    # Link Time Optimization:
    '^-flto': 0,
    # MicroBlaze Options:
    '^-mxl': 0,
    # PowerPC SPE Option:
    '^-mfloat-gprs': 0
}

# Unknown options by clang, will be skipped.

UNKNOWN_OPTIONS_MAP_REGEX = {
    '^-fallow-fetchr-insn': 0,
    '^-fcall-saved-.*': 0,
    '^-fcond-mismatch': 0,
    '^-fconserve-stack': 0,
    '^-fcrossjumping': 0,
    '^-fcse-follow-jumps': 0,
    '^-fcse-skip-blocks': 0,
    '^-ffixed-r2': 0,
    '^-ffp$': 0,
    '^-fgcse-lm': 0,
    '^-fhoist-adjacent-loads': 0,
    '^-findirect-inlining': 0,
    '^-finline-limit.*': 0,
    '^-finline-local-initialisers': 0,
    '^-fipa-sra': 0,
    '^-fno-aggressive-loop-optimizations': 0,
    '^-fno-delete-null-pointer-checks': 0,
    '^-fno-jump-table': 0,
    '^-fno-strength-reduce': 0,
    '^-fno-toplevel-reorder': 0,
    '^-fno-unit-at-a-time': 0,
    '^-fno-var-tracking-assignments': 0,
    '^-fpartial-inlining': 0,
    '^-fpeephole2': 0,
    '^-fr$': 0,
    '^-fregmove': 0,
    '^-frename-registers': 0,
    '^-freorder-functions': 0,
    '^-frerun-cse-after-loop': 0,
    '^-fs$': 0,
    '^-fsched-spec': 0,
    '^-fthread-jumps': 0,
    '^-ftree-pre': 0,
    '^-ftree-switch-conversion': 0,
    '^-ftree-tail-merge': 0,
    '^-m(no-)?abm.*$': 0,
    '^-m(no-)?sdata.*$': 0,
    '^-m(no-)?spe.*': 0,
    '^-m(no-)?string$': 0,
    '^-m(no-)?dsbt': 0,
    '^-m(no-)?fixed-ssp': 0,
    '^-m(no-)?pointers-to-nested-functions': 0,
    '^-mpcrel-func-addr': 0,
    '^-maccumulate-outgoing-args': 0,
    '^-mcall-aixdesc': 0,
    '^-mppa3-addr-bug': 0,
    '^-mtraceback=.*': 0,
    '^-mtext=.*': 0,
    '^-misa=.*': 0,
    '^-mfix-cortex-m3-ldrd$': 0,
    '^-mmultiple$': 0,
    '^-msahf$': 0,
    '^-mthumb-interwork$': 0,
    '^-mupdate$': 0,

    # Deprecated ARM specific option
    # to Generate a stack frame that is compliant
    # with the ARM Procedure Call Standard.
    '^-mapcs': 0,
    '^-fno-merge-const-bfstores$': 0,
    '^-fno-ipa-sra$': 0,
    '^-mno-thumb-interwork$': 0,
    # ARM specific option.
    # Prevent the reordering of
    # instructions in the function prologue.
    '^-mno-sched-prolog': 0,
    # This is not unknown but we want to preserve asserts to improve the
    # quality of analysis.
    '^-DNDEBUG$': 0
}


class ActionType(object):
    LINK = 0
    COMPILE = 1
    PREPROCESS = 2
    INFO = 3

    @classmethod
    def to_string(cls, num):
        if num == cls.LINK:
            return 'Link'
        if num == cls.COMPILE:
            return 'Compile'
        if num == cls.PREPROCESS:
            return 'Preprocess'
        if num == cls.INFO:
            return 'Info'
        return None


class OptionParserResult(object):
    """
    Contain the compiler arguments which can be forwarded to clang
    or clang tidy after filtering or changing the original compiler arguments.
    """
    def __init__(self):
        self._action = ActionType.COMPILE
        self._compile_opts = []
        self._link_opts = []
        self._files = []
        self._arch = ''
        self._target = ''
        self._lang = None
        self._output = ''
        self._compiler = None

    def __str__(self):
        return ('action_type: {}\ncompiler options: {}\n'
                'linker options: {}\nfiles: {}\narch: {}\n'
                'lang: {}\nout: {}\n') \
            .format(ActionType.to_string(self._action),
                    ' '.join(self._compile_opts),
                    ' '.join(self._link_opts),
                    ' '.join(self._files),
                    self._arch,
                    self._lang,
                    self._output)

    @property
    def compiler(self):
        return self._compiler

    @compiler.setter
    def compiler(self, value):
        self._compiler = value

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, value):
        self._action = value

    @property
    def compile_opts(self):
        return self._compile_opts

    @compile_opts.setter
    def compile_opts(self, value):
        self._compile_opts = value

    @property
    def link_opts(self):
        return self._link_opts

    @link_opts.setter
    def link_opts(self, value):
        self._link_opts = value

    @property
    def files(self):
        return self._files

    @files.setter
    def files(self, value):
        self._files = value

    @property
    def arch(self):
        return self._arch

    @arch.setter
    def arch(self, value):
        self._arch = value

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, value):
        self._target = value

    @property
    def lang(self):
        return self._lang

    @lang.setter
    def lang(self, value):
        self._lang = value

    @property
    def output(self):
        return self._output

    @output.setter
    def output(self, value):
        self._output = value


class OptionIterator(object):
    """
    Iterate over the compilation arguments.
    """
    def __init__(self, args):
        self._item = None
        self._it = iter(args)

    def next(self):
        self._item = next(self._it)
        return self  # ._item

    def __iter__(self):
        return self

    @property
    def item(self):
        return self._item


def arg_check(it, result):
    def regex_match(string, pattern):
        regexp = re.compile(pattern)
        match = regexp.match(string)
        return match is not None

    # Handler functions for options.
    def append_to_list(table, target_list, regex=False):
        """ Append n item from iterator to to result[att_name] list."""

        def wrapped(value):
            def append_n(size):
                target_list.append(it.item)
                for _ in range(size):
                    next(it)
                    target_list.append(it.item)

            if regex:
                for pattern in table:
                    if regex_match(value, pattern):
                        append_n(table[pattern])
                        return True
            elif value in table:
                append_n(table[value])
                return True
            return False

        return wrapped

    def append_merged_to_list(table, target_list):
        """ Append one or two item to the list.
              1: if there is no space between two option.
              2: otherwise.
        """

        def wrapped(value):
            for pattern in table:
                match = re.match(pattern, value)
                if match is not None:
                    tmp = it.item
                    if match.group(1) == '':
                        next(it)
                        tmp = tmp + it.item
                    target_list.append(tmp)
                    return True
            return False

        return wrapped

    def append_to_list_from_file(arg, target_list):
        """ Append items from file to to result[att_name] list."""

        def wrapped(value):
            if value == arg:
                next(it)
                with open(it.item) as file:
                    for line in file:
                        target_list.append(line.strip())
                return True
            return False

        return wrapped

    def append_replacement_to_list(table, target_list, regex=False):
        """ Append replacement items from table to to result[att_name] list."""

        def wrapped(value):
            def append_replacement(items):
                for item in items:
                    target_list.append(item)
                next(it)

            if regex:
                for pattern in table:
                    if regex_match(value, pattern):
                        append_replacement(table[pattern])
                        return True
            elif value in table:
                append_replacement(table[value])
                return True
            return False

        return wrapped

    def set_attr(arg, obj, attr_name, attr_value=None, regex=None):
        """ Set an attr value. If no value given then
        read next from iterator."""
        def wrapped(value):
            if (regex and regex_match(value, arg)) or value == arg:
                tmp = attr_value
                if attr_value is None:
                    next(it)
                    tmp = it.item
                setattr(obj, attr_name, tmp)
                return True
            return False

        return wrapped

    def skip(table, regex=False):
        """ Skip n item in iterator."""

        def wrapped(value):
            def skip_n(size):
                for _ in range(size):
                    next(it)

            if regex:
                for pattern in table:
                    if regex_match(value, pattern):
                        return True
            elif value in table:
                skip_n(table[value])
                return True
            return False

        return wrapped

    # Defines handler functions for tables and single options.
    arg_collection = [
        append_replacement_to_list(REPLACE_OPTIONS_MAP, result.compile_opts),
        skip(UNKNOWN_OPTIONS_MAP_REGEX, True),
        skip(IGNORED_OPTION_MAP),
        skip(IGNORED_OPTION_MAP_REGEX, True),
        set_attr('-x', result, 'lang'),
        set_attr('-o', result, 'output'),
        set_attr('-arch', result, 'arch'),
        set_attr('-c', result, 'action', ActionType.COMPILE),
        set_attr('^-(E|M[T|Q|F|J|P|V|M]*)$', result, 'action',
                 ActionType.PREPROCESS, True),
        set_attr('-print-prog-name', result, 'action', ActionType.INFO),
        append_to_list(COMPILE_OPTION_MAP, result.compile_opts),
        append_to_list(COMPILER_LINKER_OPTION_MAP, result.link_opts),
        append_to_list(LINKER_OPTION_MAP_REGEX, result.link_opts, True),
        append_to_list(COMPILE_OPTION_MAP_REGEX, result.compile_opts, True),
        append_merged_to_list(COMPILE_OPTION_MAP_MERGED, result.compile_opts),
        append_merged_to_list(LINK_OPTION_MAP_MERGED, result.link_opts),
        skip(LINKER_OPTION_MAP),
        append_to_list_from_file('-filelist', result.files),
        append_to_list({'^[^-].+': 0}, result.files, True)]

    for coll in arg_collection:
        res = coll(it.item)
        if res:
            return True

    # Unhandled compilation argument found.
    LOG.debug("Unhandled argument: " + str(it.item))
    return False


def parse_options(args):
    """ Requires a full compile command with the compiler,
    not only arguments."""

    # Keep " characters.
    args = args.replace(r'"', r'"\"')

    result_map = OptionParserResult()

    # The first element in the list is the compiler skip it from parsing.
    for it in OptionIterator(shlex.split(args)[1:]):
        arg_check(it, result_map)

    for idx, opt in enumerate(result_map.compile_opts):
        if '"' in opt:
            # Arguments with a space in them are given back in a way
            # (-DVAR="val ue") that they need an extra escape round. We can't
            # do this earlier because shlex would undo these changes and
            # mess up the result.
            result_map.compile_opts[idx] = opt.replace('"', r'"\"')

    result_map.compiler = shlex.split(args)[0]

    #  If the compiler is C++ (contains ++ in its name)
    #  we set the language explicitly to c++.
    cpp_regex = re.compile(r'.*\+\+.*')
    if cpp_regex.match(result_map.compiler) is not None:
        result_map.lang = 'c++'

    is_source = False
    for source_file in result_map.files:
        lang = get_language(os.path.splitext(source_file)[1].rstrip('"'))
        if lang:
            is_source = True
            # If lang is not set already during the argument parsing
            # set it based on the source file extension.
            if result_map.lang is None:
                result_map.lang = lang
            break

    if result_map.lang:
        LOG.debug("Detected language" + result_map.lang)

    # If there are no source files in the compilation argument
    # handle it as a link command.
    if not is_source:
        result_map.action = ActionType.LINK

    return result_map


def get_language(extension):
    mapping = {'.c': 'c',
               '.cp': 'c++',
               '.cpp': 'c++',
               '.cxx': 'c++',
               '.txx': 'c++',
               '.cc': 'c++',
               '.C': 'c++',
               '.ii': 'c++',
               '.m': 'objective-c',
               '.mm': 'objective-c++'}
    lang = mapping.get(extension) if extension in mapping else None
    return lang

#!/usr/bin/env python -u
# encoding: utf-8

# This is a rewrite of latexErrWarn.py
#
# Goals:
#
#   1. Modularize the processing of a latex run to better capture and parse
#      errors
#   2. Replace latexmk
#   3. Provide a nice pushbutton interface for manually running
#      latex, bibtex, makeindex, and viewing
#
# Overview:
#
#    Each tex command has its own class that parses the output from that
#    program.  Each of these classes extends the TexParser class which provides
#    default methods:
#
#       parseStream
#       error
#       warning
#       info
#
#   The parseStream method reads each line from the input stream matches
#   against a set of regular expressions defined in the patterns dictionary. If
#   one of these patterns matches then the corresponding method is called. This
#   method is also stored in the dictionary. Pattern matching callback methods
#   must each take the match object as well as the current line as a parameter.
#
#   To enable debug mode without modifying this file:
#
#       defaults write com.macromates.textmate latexDebug 1
#
#   Progress:
#
#       7/17/07  -- Brad Miller
#
#       Implemented  TexParse, BibTexParser, and LaTexParser classes see the
#       TODO's sprinkled in the code below
#
#       7/24/07  -- Brad Miller
#
#       Spiffy new configuration window added
#       pushbutton interface at the end of the latex output is added the
#       confusing mass of code that was Typeset & View has been replaced by
#       this one
#
#   Future:
#
#       Think about replacing latexmk with a simpler python version.  If only
#       rubber worked reliably..

# -- Imports ------------------------------------------------------------------

import sys

from glob import glob
from os import chdir, getenv, putenv, remove
from os.path import basename, dirname, exists, isfile, join, normpath, realpath
from re import compile, match
from subprocess import call, check_output, Popen, PIPE, STDOUT
from sys import argv, exit, stderr, stdout
from urllib import quote

from texparser import (BibTexParser, BiberParser, ChkTeXParser, LaTexParser,
                       MakeGlossariesParser, ParseLatexMk, TexParser)
from tmprefs import Preferences

# -- Module Import ------------------------------------------------------------

reload(sys)
sys.setdefaultencoding("utf-8")


# -- Global Variables ---------------------------------------------------------

DEBUG = False


# -- Functions ----------------------------------------------------------------

def expand_name(filename, program='pdflatex'):
    """Get the expanded file name for a certain tex file.

    Arguments:

        filename

                The name of the file we want to expand.

        program

                The name of the tex program for which we want to expand the
                name of the file.

    Returns: ``str``

    Examples:

        >>> expand_name('Tests/TeX/text.tex')
        './Tests/TeX/text.tex'
        >>> expand_name('non_existent_file.tex')
        ''

    """
    stdout.flush()
    run_object = Popen("kpsewhich -progname='{}' '{}'".format(
        program, filename), shell=True, stdout=PIPE)
    return run_object.stdout.read().strip()


def run_bibtex(texfile, verbose=False):
    """Run bibtex for a certain tex file.

    Run bibtex for ``texfile`` and return the following values:

    - The return value of the bibtex runs done by this function: This value
      will be ``0`` after a successful run. Any other value indicates that
      there were some kind of problems.

    - Fatal error: Specifies if there was a fatal error while processing the
      bibliography.

    - Errors: The number of non-fatal errors encountered while processing the
      bibliography

    - Warnings: The number of warnings found while running this function

    Arguments:

        texfile

            Specifies the name of the tex file. This information will be used
            to find the bibliography.

        verbose

            Specifies if the output by this function should be verbose.


    Returns: ``(int, bool, int, int)``

    Examples:

        >>> chdir('Tests/TeX')
        >>> run_bibtex('external_bibliography.tex') # doctest:+ELLIPSIS
        <h4>Processing: ...
        ...
        (0, False, 0, 0)
        >>> chdir('../..')

    """
    name_without_suffix = texfile[:texfile.rfind('.')]
    directory = dirname(texfile) if dirname(texfile) else '.'
    regex_auxfiles = (r'.*/({}|bu\d+)\.aux$'.format(name_without_suffix))
    auxfiles = [f for f in glob("{}/*.aux".format(directory))
                if match(regex_auxfiles, f)]

    stat, fatal, errors, warnings = 0, False, 0, 0
    for bib in auxfiles:
        print('<h4>Processing: {} </h4>'.format(bib))
        run_object = Popen("bibtex '{}'".format(bib), shell=True, stdout=PIPE,
                           stdin=PIPE, stderr=STDOUT, close_fds=True)
        bp = BibTexParser(run_object.stdout, verbose)
        f, e, w = bp.parseStream()
        fatal |= f
        errors += e
        warnings += w
        stat |= run_object.wait()
    return stat, fatal, errors, warnings


def run_biber(texfile, verbose=False):
    """Run biber for a certain tex file.

    The interface for this function is exactly the same as the one for
    ``run_bibtex``. For the list of arguments and return values please take a
    look at the doc-string of ``run_bibtex``.

    Examples:

        >>> chdir('Tests/TeX')
        >>> run_biber('external_bibliography_biber.tex') # doctest:+ELLIPSIS
        <...
        ...
        (0, False, 0, 0)
        >>> chdir('../..')

    """
    file_no_suffix = get_filename_without_extension(texfile)
    run_object = Popen("biber '{}'".format(file_no_suffix), shell=True,
                       stdout=PIPE, stdin=PIPE, stderr=STDOUT, close_fds=True)
    bp = BiberParser(run_object.stdout, verbose)
    fatal, errors, warnings = bp.parseStream()
    stat = run_object.wait()
    return stat, fatal, errors, warnings


def run_latex(ltxcmd, texfile, verbose=False):
    """Run the flavor of latex specified by ltxcmd on texfile.

    This function returns:

        - the return value of ``ltxcmd``,

        - a value specifying if there were any fatal flaws (``True``) or not
          (``False``), and

        - the number of errors and

        - the number of warnings encountered while processing ``texfile``.

    Arguments:

        ltxcmd

            The latex command which should be used translate ``texfile``.

        texfile

            The path of the tex file which should be translated by ``ltxcmd``.

    Returns: ``(int, bool, int, int)``

    Examples:

        >>> chdir('Tests/TeX')
        >>> run_latex(ltxcmd='pdflatex',
        ...           texfile='external_bibliography.tex') # doctest:+ELLIPSIS
        <h4>...
        ...
        (0, False, 0, 0)
        >>> chdir('../..')

    """
    if DEBUG:
        print("<pre>run_latex: {} '{}'</pre>".format(ltxcmd, texfile))
    run_object = Popen("{} '{}'".format(ltxcmd, texfile), shell=True,
                       stdout=PIPE, stdin=PIPE, stderr=STDOUT, close_fds=True)
    lp = LaTexParser(run_object.stdout, verbose, texfile)
    fatal, errors, warnings = lp.parseStream()
    stat = run_object.wait()
    return stat, fatal, errors, warnings


def run_makeindex(filename):
    """Run the makeindex command.

    Generate the index for the given file returning

        - the return value of ``makeindex``,

        - a value specifying if there were any fatal flaws (``True``) or not
          (``False``), and

        - the number of errors and

        - the number of warnings encountered while processing ``filename``.

    Arguments:

        filename

            The name of the tex file for which we want to generate an index.

    Returns: ``(int, bool, int, int)``

    Examples:

        >>> chdir('Tests/TeX')
        >>> run_makeindex('makeindex.tex') # doctest:+ELLIPSIS
        This is makeindex...
        ...
        (0, False, 0, 0)
        >>> chdir('../..')

    """
    run_object = Popen("makeindex '{}.idx'".format(
                       get_filename_without_extension(filename)), shell=True,
                       stdout=PIPE, stdin=PIPE, stderr=STDOUT, close_fds=True)
    ip = TexParser(run_object.stdout, True)
    fatal, errors, warnings = ip.parseStream()
    stat = run_object.wait()
    return stat, fatal, errors, warnings


def run_makeglossaries(filename):
    """Run makeglossaries for the given file.

    The interface of this function is exactly the same as the one for
    ``run_makeindex``. For the list of arguments and return values, please
    take a look at ``run_makeindex``.

    Examples:

        >>> chdir('Tests/TeX')
        >>> run_makeglossaries('makeglossaries.tex') # doctest:+ELLIPSIS
        <h2>Make Glossaries...
        ...
        (0, False, 0, 0)
        >>> chdir('../..')

    """
    run_object = Popen("makeglossaries '{}'".format(
                       get_filename_without_extension(filename)), shell=True,
                       stdout=PIPE, stdin=PIPE, stderr=STDOUT, close_fds=True)
    bp = MakeGlossariesParser(run_object.stdout, True)
    fatal, errors, warnings = bp.parseStream()
    stat = run_object.wait()
    return stat, fatal, errors, warnings


def get_app_path(application, tm_support_path=getenv("TM_SUPPORT_PATH")):
    """Get the absolute path of the specified application.

    This function returns either the path to ``application`` or ``None`` if
    the specified application was not found.

    Arguments:

        application

            The application for which this function should return the path

        tm_support_path

            The path to the “Bundle Support” bundle

    Returns: ``str``

        # We assume that Skim is installed in the ``/Applications`` folder
        >>> get_app_path('Skim')
        '/Applications/Skim.app'
        >>> get_app_path('NonExistentApp') # Returns ``None``

    """
    try:
        return check_output("'{}/bin/find_app' '{}.app'".format(
                            tm_support_path, application),
                            shell=True, universal_newlines=True).strip()
    except:
        return None


def get_app_path_and_sync_command(viewer, path_pdf, path_tex_file,
                                  line_number):
    """Get the path and pdfsync command for the specified viewer.

    This function returns a tuple containing

        - the full path to the application, and

        - a command which can be used to show the PDF output corresponding to
          ``line_number`` inside tex file.

    If one of these two variables could not be determined, then the
    corresponding value will be set to ``None``.

    Arguments:

        viewer:

            The name of the PDF viewer application.

        path_pdf:

            The path to the PDF file generated from the tex file located at
            ``path_tex_file``.

        path_tex_file

            The path to the tex file for which we want to generate the pdfsync
            command.

        line_number

            The line in the tex file for which we want to get the
            synchronization command.

    Examples:

        # We assume that Skim is installed
        >>> get_app_path_and_sync_command('Skim', 'test.pdf', 'test.tex', 1)
        ...     # doctest:+ELLIPSIS +NORMALIZE_WHITESPACE
        ('.../Skim.app',
         "'.../Skim.app/.../displayline' 1 'test.pdf' 'test.tex'")

        # Preview has no pdfsync support
        >>> get_app_path_and_sync_command('Preview', 'test.pdf', 'test.tex', 1)
        ('/Applications/Preview.app', None)

    """
    sync_command = None
    path_to_viewer = get_app_path(viewer)
    if path_to_viewer and viewer == 'Skim':
        sync_command = ("'{}/Contents/SharedSupport/displayline' ".format(
                        path_to_viewer) + "{} '{}' '{}'".format(line_number,
                        path_pdf, path_tex_file))
    if DEBUG:
        print("Path to PDF viewer:      {}".format(path_to_viewer))
        print("Synchronization command: {}".format(sync_command))
    return path_to_viewer, sync_command


def refresh_viewer(viewer, pdf_path):
    """Tell the specified PDF viewer to refresh the PDF output.

    If the viewer does not support refreshing PDFs (e.g. “Preview”) then this
    command will do nothing. This command will return a non-zero value if the
    the viewer could not be found or the PDF viewer does not support a “manual”
    refresh.

    Arguments:

        viewer

            The viewer for which we want to refresh the output of the PDF file
            specified in ``pdf_path``.

        pdf_path

            The path to the PDF file for which we want to refresh the output.

    Returns: ``int``

    Examples:

        >>> refresh_viewer('Skim', 'test.pdf')
        <p class="info">Tell Skim to refresh 'test.pdf'</p>
        0

    """
    print('<p class="info">Tell {} to refresh \'{}\'</p>').format(viewer,
                                                                  pdf_path)
    if viewer == 'Skim':
        return call("osascript -e 'tell application \"{}\" ".format(viewer) +
                    "to revert (documents whose path is " +
                    "\"{}\")'".format(pdf_path), shell=True)
    elif viewer == 'TeXShop':
        return call("osascript -e 'tell application \"{}\" ".format(viewer) +
                    "to tell documents whose path is " +
                    "\"{}\" to refreshpdf'".format(pdf_path), shell=True)
    return 1


def run_viewer(viewer, file_name, file_path, suppress_pdf_output_textmate,
               use_pdfsync, line_number,
               tm_bundle_support=getenv('TM_BUNDLE_SUPPORT')):
    """Open the PDF viewer containing the PDF generated from ``file_name``.

    If ``use_pdfsync`` is set to ``True`` and the ``viewer`` supports pdfsync
    then the part of the PDF corresponding to ``line_number`` will be opened.
    The function returns the exit value of the shell command used to display
    the PDF file.

    Arguments:

        viewer

            Specifies which PDF viewer should be used to display the PDF

        file_name

            The file name of the tex or pdf file.

        file_path

            The path to the folder which contains the tex file

        suppress_pdf_output_textmate

            This variable is only used when ``viewer`` is set to ``TextMate``.
            If it is set to ``True`` then TextMate will not try to display the
            generated PDF.

        tm_bundle_support

            The location of the “LaTeX Bundle” support folder

    Returns: ``int``

    Examples:

        >>> chdir('Tests/TeX')
        >>> call("pdflatex makeindex.tex > /dev/null", shell=True)
        0
        >>> run_viewer('Skim', 'makeindex.tex', '.',
        ...            suppress_pdf_output_textmate=None, use_pdfsync=True,
        ...            line_number=10, tm_bundle_support=realpath('..'))
        0
        >>> chdir('../..')

    """
    status = 0
    path_file = "{}/{}".format(file_path, file_name)
    path_pdf = "{}/{}.pdf".format(file_path,
                                  get_filename_without_extension(file_name))

    if viewer == 'TextMate':
        if not suppress_pdf_output_textmate:
            if isfile(path_pdf):
                print('''<script type="text/javascript">
                         window.location="file://{}"
                         </script>'''.format(quote(path_pdf)))
            else:
                print("File does not exist: '{}'".format(path_pdf))
    else:
        path_to_viewer, sync_command = get_app_path_and_sync_command(
            viewer, path_pdf, path_file, line_number)
        # PDF viewer is installed and it supports pdfsync
        if sync_command and use_pdfsync:
            call(sync_command, shell=True)
        # PDF viewer is installed
        elif path_to_viewer:
            if use_pdfsync:
                print("{} does not supported pdfsync".format(viewer))
            # If this is not done, the next line will thrown an encoding
            # exception when the PDF file contains non-ASCII characters.
            viewer = viewer.encode('utf-8')
            pdf_already_open = not(bool(
                call("'{}/bin/check_open' '{}' '{}'".format(tm_bundle_support,
                     viewer, path_pdf), shell=True)))
            if pdf_already_open:
                refresh_viewer(viewer, path_pdf)
            else:
                status = call("open -a '{}.app' '{}'".format(viewer, path_pdf),
                              shell=True)
        # PDF viewer could not be found
        else:
            print('<strong class="error"> {} does not appear '.format(viewer) +
                  'to be installed on your system.</strong>')
    return status


def determine_typesetting_directory(ts_directives,
                                    master_document=getenv('TM_LATEX_MASTER'),
                                    tex_file=getenv('TM_FILEPATH')):
    """Determine the proper directory for typesetting the current document.

    The typesetting directory is set according to the first applicable setting
    in the following list:

        1. The typesetting directive specified via the line

                ``%!TEX root = path_to_tex_file``

            somewhere in your tex file

        2. the value of ``TM_LATEX_MASTER``, or
        3. the location of the current tex file.

    Arguments:

        ts_directives

            A dictionary containing typesetting directives. If it contains the
            key ``root`` then the path in the value of ``root`` will be used
            as typesetting directory.

        master_document

            Specifies the location of the master document
            (``TM_LATEX_MASTER``).

        tex_file

            The location of the current tex file

    Returns: ``str``

    Examples:

        >>> ts_directives = {'root' : 'Tests/makeindex.tex'}
        >>> determine_typesetting_directory(ts_directives) # doctest:+ELLIPSIS
        '.../Tests'
        >>> determine_typesetting_directory( # doctest:+ELLIPSIS
        ...     {}, master_document='Tests/external_bibliography')
        '.../Tests'

    """
    tex_file_dir = dirname(tex_file)

    if 'root' in ts_directives:
        master_path = dirname(ts_directives['root'])
    elif master_document:
        master_path = dirname(master_document)
    else:
        master_path = tex_file_dir

    if master_path == '' or not master_path.startswith('/'):
        master_path = normpath(realpath(join(tex_file_dir, master_path)))

    if DEBUG:
        print("<pre>Typesetting Directory = {}</pre>".format(master_path))

    return master_path


def find_file_to_typeset(tyesetting_directives,
                         master_document=getenv('TM_LATEX_MASTER'),
                         tex_file=getenv('TM_FILEPATH')):
    """Determine which tex file to typeset.

    This is determined according to the following options:

       - %!TEX root directive
       - The ``TM_LATEX_MASTER`` environment variable
       - The environment variable ``TM_FILEPATH``

       This function returns a tuple containing the name and the path to the
       file which should be typeset.

    Arguments:

        ts_directives

            A dictionary containing typesetting directives. If it contains the
            key ``root`` then the value of ``root`` will be used for
            determining the file which should be typeset.

        master_document

            Specifies the location of the master document
            (``TM_LATEX_MASTER``).

        tex_file

            The location of the current tex file

    Returns: (``str``, ``str``)

    Examples:

        >>> find_file_to_typeset({'root': 'Tests/makeindex.tex'})
        ...     # doctest:+ELLIPSIS
        ('makeindex.tex', '.../Tests')
        >>> find_file_to_typeset({},
        ...     master_document='../packages.tex',
        ...     tex_file='Tests/input/packages_input1.tex') # doctest:+ELLIPSIS
        ('packages.tex', '.../Tests')
        >>> find_file_to_typeset({'root': '../packages.tex'}, None,
        ...     tex_file='Tests/input/packages_input1.tex') # doctest:+ELLIPSIS
        ('packages.tex', '.../Tests')
        >>> find_file_to_typeset({}, None, 'Tests/packages.tex')
        ...     # doctest:+ELLIPSIS
        ('packages.tex', '.../Tests')

    """
    if 'root' in tyesetting_directives:
        master = tyesetting_directives['root']
    elif master_document:
        master = master_document
    else:
        master = tex_file

    if DEBUG:
        print('<pre>Master File = {}</pre>'.format(master))
    return (basename(master),
            determine_typesetting_directory(tyesetting_directives,
                                            master_document, tex_file))


def find_tex_packages(file_name):
    """Find packages included by the given file.

    This function searches for packages in:

        1. The preamble of ``file_name``, and
        2. files included in the preamble of ``file_name``.

    Arguments:

        file_name

            The path of the file which should be searched for packages.

    Returns: ``{str}``

    Examples:

        >>> chdir('Tests/TeX')
        >>> packages = find_tex_packages('packages.tex')
        >>> isinstance(packages, set)
        True
        >>> sorted(packages) # doctest:+NORMALIZE_WHITESPACE
        ['csquotes', 'framed', 'mathtools', 'polyglossia', 'unicode-math',
         'xcolor']
        >>> chdir('../..')

    """
    try:
        file = open(expand_name(file_name))
    except:
        print('<p class="error">Error: Could not open ' +
              '{} to check for packages</p>'.format(file_name))
        print('<p class="error">This is most likely a problem with ' +
              'TM_LATEX_MASTER</p>')
        exit(1)
    option_regex = r'\[[^\{]+\]'
    argument_regex = r'\{([^\}]+)\}'
    input_regex = compile(r'[^%]*?\\input{}'.format(argument_regex))
    package_regex = compile(r'[^%]*?\\usepackage(?:{})?{}'.format(
                            option_regex, argument_regex))
    begin_regex = compile(r'[^%]*?\\begin\{document\}')

    # Search for packages and included files in the tex document
    included_files = []
    packages = []
    for line in file:
        match_input = match(input_regex, line)
        match_package = match(package_regex, line)
        if match_input:
            included_files.append(match_input.group(1))
        if match_package:
            packages.append(match_package.group(1))
        if match(begin_regex, line):
            break

    # Search for packages in all files till we find the beginning of the
    # document and therefore the end of the preamble
    included_files = [included_file if included_file.endswith('.tex')
                      else '{}.tex'.format(included_file)
                      for included_file in included_files]
    match_begin = False
    while included_files and not match_begin:
        try:
            file = open(expand_name(included_files.pop()))
        except:
            print('<p class="warning">Warning: Could not open ' +
                  '{} to check for packages</p>'.format(included_file))

        for line in file:
            match_package = match(package_regex, line)
            match_begin = match(begin_regex, line)
            if match_package:
                packages.append(match_package.group(1))
            if match_begin:
                break

    # Split package definitions of the form 'package1, package2' into
    # 'package1', 'package2'
    package_list = []
    for package in packages:
        package_list.extend([package.strip()
                             for package in package.split(',')])

    if DEBUG:
        print('<pre>TEX package list = {}</pre>'.format(package_list))
    return set(package_list)


def find_tex_directives(texfile=getenv('TM_FILEPATH')):
    """Build a dictionary of %!TEX directives.

    The main ones we are concerned with are:

       root

           Specifies a root file to run tex on for this subsidiary

       TS-program

            Tells us which latex program to run

       TS-options

           Options to pass to TS-program

       encoding

            The text encoding of the tex file

    Arguments:

        texfile

            The initial tex file which should be searched for tex directives.
            If this file contains a “root” directive, then the file specified
            in this directive will be searched next.

    Returns: ``{str: str}``

    Examples:

        >>> chdir('Tests/TeX')
        >>> find_tex_directives('input/packages_input1.tex')
        ...     # doctest:+ELLIPSIS
        {'root': .../Tests/TeX/packages.tex', 'TS-program': 'xelatex'}
        >>> find_tex_directives('makeindex.tex')
        {}
        >>> chdir('../..')

    """
    root_chain = [texfile]
    directive_regex = compile(r'%!TEX\s+([\w-]+)\s?=\s?(.*)')
    directives = {}
    while True:
        lines = [line for (line_number, line) in enumerate(open(texfile))
                 if line_number < 20]
        new_directives = {directive.group(1): directive.group(2).rstrip()
                          for directive
                          in [directive_regex.match(line) for line in lines]
                          if directive}
        directives.update(new_directives)
        if 'root' in new_directives:
            root = directives['root']
            new_tex_file = (root if root.startswith('/') else
                            realpath(join(dirname(texfile), root)))
            directives['root'] = new_tex_file
        else:
            break

        if new_tex_file in root_chain:
            print('''<p class="error"> There is a loop in your "%!TEX root ="
                                       directives.</p>
                     <p class="error"> Chain: {}</p>
                     <p class="error"> Exiting.</p>'''.format(root_chain))
            exit(-1)
        else:
            texfile = new_tex_file
            root_chain.append(texfile)

    if DEBUG:
        print('<pre>%!TEX Directives: {}</pre>'.format(directives))

    return directives


def construct_engine_options(ts_directives, tm_preferences, synctex=True):
    """Construct a string of command line options.

    The options come from two different sources:

        - %!TEX TS-options directive in the file
        - Options specified in the preferences of the LaTeX bundle

    In any case ``nonstopmode`` is set as is ``file-line-error-style``.

    Arguments:

        ts_directives

            A dictionary containing typesetting directives. If it contains the
            key ``TS-options`` then this value will be used to construct the
            options.

        tm_preferences

            A ``Preferences`` object containing preference items from
            TextMate. The settings specified in the key ``latexEngineOptions``
            will be used to extend the options only if ts_directives does not
            contain typesetting options. Otherwise the settings specified in
            this item will be ignored.

        synctex

            Specifies if synctex should be used for typesetting or not.


    Returns: ``str``

    Examples:

        # We “simulate” the ``Preference`` object in the following examples by
        # using a dictionary
        >>> tm_preferences = {'latexEngineOptions': ''}
        >>> construct_engine_options({}, tm_preferences, True)
        ...     # doctest:+ELLIPSIS
        '-interaction=nonstopmode -file-line-error-style -synctex=1'
        >>> construct_engine_options({'TS-options': '-draftmode'},
        ...                          tm_preferences, False)
        '-interaction=nonstopmode -file-line-error-style -draftmode'
        >>> construct_engine_options({'TS-options': '-draftmode'},
        ...                          {'latexEngineOptions': '-8bit'}, False)
        '-interaction=nonstopmode -file-line-error-style -draftmode'
        >>> construct_engine_options({}, {'latexEngineOptions': '-8bit'})
        '-interaction=nonstopmode -file-line-error-style -synctex=1 -8bit'

    """
    options = "-interaction=nonstopmode -file-line-error-style{}".format(
        ' -synctex=1' if synctex else '')

    if 'TS-options' in ts_directives:
        options += ' {}'.format(ts_directives['TS-options'])
    else:
        latex_options = tm_preferences['latexEngineOptions'].strip()
        options += ' {}'.format(latex_options) if latex_options else ''

    if DEBUG:
        print('<pre>Engine options = {}</pre>'.format(options))
    return options


def construct_engine_command(ts_directives, tm_preferences, packages):
    """Decide which tex engine to use according to the given arguments.

    The value of the engine is calculated according to the first applicable
    setting in the following list:

       1. The value of ``TS-program`` specified inside the tex file.

       2. The list of included packages. If one of the used packages only works
          with a special typesetting engine, then this engine will be returned.

       3. The value of the latex engine specified inside the preferences of
          the LaTeX bundle.

    Arguments:

        ts_directives

            A dictionary containing typesetting directives. If it contains the
            key ``TS-program`` then this value will be used as the typesetting
            engine.

        tm_preferences

            A ``Preferences`` object containing preference items from
            TextMate. The settings specified in the key ``latexEngine`` will
            be used as typesetting engine if ``TS-program`` is not set and non
            of the packages contain engine-specific code.

        packages

            The packages included in the tex file, which should be typeset.

    Returns: ``str``

    Examples:

        # We “simulate” the ``Preference`` object in the following examples by
        # using a dictionary
        >>> tm_preferences = {'latexEngine': 'latex'}
        >>> construct_engine_command({'TS-program': 'pdflatex'},
        ...                          tm_preferences, set())
        'pdflatex'
        >>> construct_engine_command({}, tm_preferences, {'fontspec'})
        'xelatex'
        >>> construct_engine_command({}, tm_preferences, set())
        'latex'

    """
    latexIndicators = {'pstricks', 'xyling', 'pst-asr', 'OTtablx', 'epsfig'}
    xelatexIndicators = {'xunicode', 'fontspec'}

    if 'TS-program' in ts_directives:
        engine = ts_directives['TS-program']
    elif packages.intersection(latexIndicators):
        engine = 'latex'
    elif packages.intersection(xelatexIndicators):
        engine = 'xelatex'
    else:
        engine = tm_preferences['latexEngine']

    if call("type {} > /dev/null".format(engine), shell=True) != 0:
        print('''<p class="error">Error: {} was not found,
                 Please make sure that LaTeX is installed and your PATH is
                 setup properly.</p>'''.format(engine))
        exit(1)

    return engine


def get_filename_without_extension(filename):
    """Get the given file name without its extension.

    If ``filename`` has no extensions then the unchanged file name will be
    returned.

    Arguments:

        file_name

            The path of some file, either with or without extension.

    Returns: ``str``


    Examples:

        >>> get_filename_without_extension('../hello_world.tex')
        '../hello_world'
        >>> get_filename_without_extension('Makefile')
        'Makefile'

    """
    suffix_index = filename.rfind(".")
    return filename[:suffix_index] if suffix_index > 0 else filename


def write_latexmkrc(engine, options, location='/tmp/latexmkrc'):
    """Create a “latexmkrc” file that uses the proper engine and arguments.

    Arguments:

        engine

            A string specifying the engine which should be used by ``latexmk``.

        options

            A string specifying the arguments which should be used by
            ``engine``.

        location

            The path to the location where the ``latexmkrc`` file should be
            saved.

    Examples:

        >>> write_latexmkrc(engine='latex', options='8bit')
        >>> with open('/tmp/latexmkrc') as latexmkrc_file:
        ...     print(latexmkrc_file.read())  # doctest:+ELLIPSIS
        $latex = '...8bit...';
        ...

    """
    with open("/tmp/latexmkrc", 'w') as latexmkrc:
        latexmkrc.write("$latex = 'latex -interaction=nonstopmode " +
                        "-file-line-error-style {}';\n".format(options) +
                        "$pdflatex = '{} ".format(engine) +
                        "-interaction=nonstopmode " +
                        "-file-line-error-style {}';".format(options))


# -- Main ---------------------------------------------------------------------

if __name__ == '__main__':

    def bibtex():
        """Generate the bibliography for the tex file."""
        use_biber = exists('{}.bcf'.format(file_without_suffix))
        return (run_biber(texfile=filename) if use_biber else
                run_bibtex(texfile=filename))

    def index():
        """Generate the index for the tex file"""
        use_makeglossaries = exists('{}.glo'.format(file_without_suffix))
        return (run_makeglossaries(filename) if use_makeglossaries else
                run_makeindex(filename))

    def latex():
        """Run latex for the tex file."""
        engine_options = construct_engine_options(typesetting_directives,
                                                  tm_preferences, synctex)
        command = "{} {}".format(engine, engine_options)
        return run_latex(command, filename, verbose), command

    # Get preferences from TextMate
    tm_preferences = Preferences()
    number_runs = 0
    viewer_status = 0
    first_run = False
    line_number = getenv('TM_SELECTION').split(':')[0]
    number_errors = 0
    number_warnings = 0
    synctex = False
    tex_status = None
    tm_bundle_support = getenv('TM_BUNDLE_SUPPORT')
    use_latexmk = tm_preferences['latexUselatexmk']
    verbose = True if tm_preferences['latexVerbose'] == 1 else False
    viewer = tm_preferences['latexViewer']

    # Parse command line parameters...
    if len(argv) > 2:
        first_run = True  # A little hack to make the buttons work nicer.
    if len(argv) > 1:
        command = argv[1]
    else:
        stderr.write("Usage: {} tex-command first_run\n".format(argv[0]))
        exit(255)

    if int(tm_preferences['latexDebug']) == 1:
        DEBUG = True
        print('<pre>Turning on Debug</pre>')

    typesetting_directives = find_tex_directives()
    chdir(determine_typesetting_directory(typesetting_directives))

    if command == 'latex' and use_latexmk:
        command = 'latexmk'

    filename, file_path = find_file_to_typeset(typesetting_directives)
    file_without_suffix = get_filename_without_extension(filename)

    packages = find_tex_packages(filename)
    engine = construct_engine_command(typesetting_directives, tm_preferences,
                                      packages)

    synctex = not(bool(call("{} --help | grep -q synctex".format(engine),
                       shell=True)))

    texinputs = ('{}:'.format(getenv('TEXINPUTS')) if getenv('TEXINPUTS') else
                 '.::')
    texinputs += "{}/tex//".format(tm_bundle_support)
    putenv('TEXINPUTS', texinputs)

    if DEBUG:
        print('<pre>')
        print('Engine: {}'.format(engine))
        print('Command: {}'.format(command))
        print('Viewer: {}'.format(viewer))
        print('TeX Inputs: {}'.format(texinputs))
        print('Filename: {}'.format(filename))
        print('Use Latexmk: {}'.format(use_latexmk))
        print('Synctex: {}'.format(synctex))
        print('</pre>')

    if command == "version":
        process = Popen("{} --version".format(engine), stdout=PIPE, shell=True)
        print process.stdout.read().split('\n')[0]
        exit(0)

    # Print out header information to begin the run
    if not first_run:
        print('<hr>')
    print '<div id="commandOutput"><div id="preText">'

    if filename == file_without_suffix:
        print("<h2 class='warning'>Warning: LaTeX file has no extension. " +
              "See log for errors/warnings</h2>")

    if synctex and 'pdfsync' in packages:
        print("<p class='warning'>Warning: {} supports ".fomat(engine) +
              "synctex but you have included pdfsync. You can safely remove " +
              "\usepackage{pdfsync}</p>")

    # Run the command passed on the command line or modified by preferences
    if command == 'latexmk':
        engine_options = construct_engine_options(typesetting_directives,
                                                  tm_preferences, synctex)
        write_latexmkrc(engine, engine_options, '/tmp/latexmkrc')
        command = "latexmk -pdf{} -f -r /tmp/latexmkrc '{}'".format(
            'ps' if engine == 'latex' else '', filename)
        if DEBUG:
            print("Latexmk command: {}".format(command))
        process = Popen(command, shell=True, stdout=PIPE, stdin=PIPE,
                        stderr=STDOUT, close_fds=True)
        command_parser = ParseLatexMk(process.stdout, verbose, filename)
        status = command_parser.parseStream()
        fatal_error, number_errors, number_warnings = status
        tex_status = process.wait()
        remove("/tmp/latexmkrc")
        if tm_preferences['latexAutoView'] and number_errors < 1:
            viewer_status = run_viewer(
                viewer, filename, file_path,
                number_errors > 1 or number_warnings > 0
                and tm_preferences['latexKeepLogWin'],
                'pdfsync' in packages or synctex, line_number)
        number_runs = command_parser.numRuns

    elif command == 'bibtex':
        tex_status, fatal_error, number_errors, number_warnings = bibtex()

    elif command == 'index':
        tex_status, fatal_error, number_errors, number_warnings = index()

    elif command == 'clean':
        auxiliary_file_extension = [
            'acr', 'alg', 'aux', 'bbl', 'bcf', 'blg', 'fdb_latexmk', 'fls',
            'fmt', 'glg', 'gls', 'ini', 'log', 'out', 'maf', 'mtc', 'mtc1',
            'pdfsync', 'run.xml', 'synctex.gz', 'toc']
        command = 'rm -vf {}'.format(' '.join(
            ['*.' + extension for extension in auxiliary_file_extension]))
        removed_files = check_output(command, shell=True)
        print("<p>Removed: {}</p>".format(removed_files))

    elif command == 'builtin':
        # The latex, bibtex, index, latex, latex sequence should cover 80% of
        # the cases that latexmk does
        _, command = latex()
        number_runs += 1
        bibtex()
        index()
        for runs in range(2):
            status = run_latex(command, filename, verbose)
            number_runs += 1

        tex_status, fatal_error, number_errors, number_warnings = status

    elif command == 'latex':
        status, _ = latex()
        tex_status, fatal_error, number_errors, number_warnings = status
        number_runs += 1

        if engine == 'latex':
            call("dvips {0}.dvi -o '{0}.ps'".format(file_without_suffix),
                 shell=True)
            call("ps2pdf '{}.ps'".format(file_without_suffix), shell=True)
        if tm_preferences['latexAutoView'] and number_errors < 1:
            viewer_status = run_viewer(
                viewer, filename, file_path,
                number_errors > 1 or number_warnings > 0 and
                tm_preferences['latexKeepLogWin'],
                'pdfsync' in packages or synctex, line_number)

    elif command == 'view':
        viewer_status = run_viewer(
            viewer, filename, file_path,
            number_errors > 1 or number_warnings > 0 and
            tm_preferences['latexKeepLogWin'],
            'pdfsync' in packages or synctex, line_number)

    elif command == 'sync':
        if 'pdfsync' in packages or synctex:
            _, sync_command = get_app_path_and_sync_command(
                viewer, '{}.pdf'.format(file_without_suffix), filename,
                line_number)
            if sync_command:
                viewer_status = call(sync_command, shell=True)
            else:
                print("{} does not support pdfsync".format(viewer))
                viewer_status = 1

        else:
            print("Either you need to include `pdfsync.sty` in your document" +
                  "or you need to use an engine that supports pdfsync.")
            exit(206)

    elif command == 'chktex':
        command = "{} '{}'".format(command, filename)
        process = Popen(command, shell=True, stdout=PIPE, stdin=PIPE,
                        stderr=STDOUT, close_fds=True)
        parser = ChkTeXParser(process.stdout, verbose, filename)
        fatal_error, number_errors, number_warnings = parser.parseStream()
        tex_status = process.wait()

    # Check status of running the viewer
    if viewer_status != 0:
        print('<p class="error"><strong>Error {} '.format(viewer_status) +
              'opening viewer</strong></p>')

    # Check the status of any runs...
    exit_code = 0
    if tex_status != 0 or number_warnings > 0 or number_errors > 0:
        print('<p class="info">Found {} errors, and '.format(number_errors) +
              '{} warnings in {} run{}</p>'.format(number_warnings,
              number_runs, '' if number_runs == 1 else 's'))
        if tex_status:
            if tex_status > 0:
                print('<p class="info"> Command {} exited '.format(command) +
                      'with status {}'.format(tex_status))
            else:
                print('<p class="error"> Command {} exited '.format(command) +
                      'with error code {}</p>'.format(tex_status))

    # Decide what to do with the Latex & View log window
    if not tm_preferences['latexKeepLogWin']:
        if number_errors == 0 and viewer != 'TextMate':
            exit_code = 200
        else:
            exit_code = 0
    else:
        exit_code = 0

    print '</div></div>'  # Close divs `preText` and `commandOutput`

    # Output buttons at the bottom of the window
    if first_run:
        pdf_file = '{}.pdf'.format(file_without_suffix)
        use_makeglossaries = exists('{}.glo'.format(file_without_suffix))
        # only need to include the javascript library once
        texlib_location = quote('{}/bin/texlib.js'.format(tm_bundle_support))

        print('''<script src="file://{}" type="text/javascript"
                  charset="utf-8"></script>
                 <div id="texActions">
                 <input type="button" value="Re-Run {}"
                  onclick="runLatex(); return false">
                 <input type="button" value="Run Bib" onclick="runBibtex();
                  return false">'''.format(texlib_location, engine))

        print('''<input type="button" value="{}"
                  onclick="runMakeIndex(); return false">'''.format(
              'Make Glossaries' if use_makeglossaries else 'Run Makeindex'))
        print('''<input type="button" value="Clean up" onclick="runClean();
                  return false">''')

        if viewer == 'TextMate':
            print('''<input type="button" value="view in TextMate"
                      onclick="window.location='file://{}'"/>'''.format(
                  quote('{}/{}'.format(file_path, pdf_file))))
        else:
            print('''<input type="button" value="View in {}"
                     onclick="runView(); return false">'''.format(viewer))

        print('''<input type="button" value="Preferences"
                  onclick="runConfig(); return false">
                 <p>
                 <input type="checkbox" id="hv_warn" name="fmtWarnings"
                 onclick="makeFmtWarnVisible(); return false">
                 <label for="hv_warn">Show hbox, vbox Warnings </label>
                 ''')

        if use_latexmk:
            print('''<input type="checkbox" id="ltxmk_warn"
                      name="ltxmkWarnings" onclick="makeLatexmkVisible();
                      return false">
                     <label for="ltxmk_warn">Show Latexmk Messages </label>''')

        print('</p></div>')

    exit(exit_code)
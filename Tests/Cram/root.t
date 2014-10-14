-- Setup ----------------------------------------------------------------------

  $ cd "$TESTDIR";
  $ source setup_cram.sh
  $ cd ../TeX

-- Tests ----------------------------------------------------------------------

We test if the root directive (%!TEX root) works. This means that although we
call typesetting on a certain file, we translate the file specified as
`root`.

  $ TM_FILEPATH="input/packages_input1.tex"

Just try to translate the program using `latex`. The root file is
`packages.tex`

  $ output=`texmate.py latex | grep 'packages.tex' | countlines`
  $ if [ $output -ge 1 ]; then echo 'OK'; fi
  OK

Check if clean removes all auxiliary files.

  $ texmate.py clean > /dev/null
  $ ls | grep $auxiliary_files_regex
  [1]

-- Cleanup --------------------------------------------------------------------

Restore the file changes made by previous commands.

  $ git checkout *.aux *.bcf

Remove the generated PDF files

  $ rm -f *.pdf
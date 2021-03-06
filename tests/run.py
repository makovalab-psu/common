#!/usr/bin/env python3
import argparse
import difflib
import logging
import os
import pathlib
import subprocess
import sys
import types
assert sys.version_info.major >= 3, 'Python 3 required'

TESTS_DIR = pathlib.Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('tests', metavar='test_name', nargs='*',
    help='The tests to run.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  # Create the dicts holding all defined tests.

  meta_tests = get_objects_diff(GlobalsInitial, GlobalsAfterMeta)
  meta_tests['all'] = lambda name: run_test_group(simple_tests)
  meta_tests['active'] = lambda name: run_test_group(active_tests)
  meta_tests['inactive'] = lambda name: run_test_group(inactive_tests)

  active_tests = get_objects_diff(GlobalsAfterMeta, GlobalsAfterActive)
  inactive_tests = get_objects_diff(GlobalsAfterActive, GlobalsAfterInactive)
  simple_tests = add_dicts(active_tests, inactive_tests)

  all_tests = add_dicts(meta_tests, simple_tests)

  if not args.tests:
    print('Meta tests:')
    for test_name in meta_tests.keys():
      print('  '+test_name)
    print('Active tests:')
    for test_name in active_tests.keys():
      print('  '+test_name)
    print('Inactive tests:')
    for test_name in inactive_tests.keys():
      print('  '+test_name)
    return 1

  unknown_tests = []
  for test_name in args.tests:
    if test_name not in all_tests:
      unknown_tests.append(test_name)
  if unknown_tests:
    fail('Error: Test(s) "{}" unrecognized.'.format('", "'.join(unknown_tests)))

  for test_name in args.tests:
    test_fxn = all_tests[test_name]
    test_fxn(test_name)

GlobalsInitial = globals().copy()


##### Meta tests #####

GlobalsAfterMeta = globals().copy()


##### Active tests #####

def getreads_smoke(test_name):
  script_name = 'getreads.py'
  script = ROOT_DIR / script_name
  test_pairs = (
    ('smoke.fq',  'smoke.fq.out'),
    ('smoke.fa',  'smoke.fa.out'),
    ('smoke.txt', 'smoke.txt.out'),
    ('smoke.tsv', 'smoke.tsv.out'),
    ('smoke.sam', 'smoke.sam.out'),
  )
  for input_name, output_name in test_pairs:
    print(f'{test_name} ::: {script_name} ::: {input_name}\t', end='')
    result, exit_code = run_command_and_capture((script, TESTS_DIR/input_name), onerror='stderr')
    if exit_code != 0:
      print('FAILED')
    else:
      expected = read_file(TESTS_DIR/output_name)
      if result != expected:
        print('FAILED')
        for line in trimmed_diff(expected.splitlines(), result.splitlines()):
          print(line)
      else:
        print('success')


def parse_test_align(test_name):
  script_name = 'parse-test-align.py'
  script = ROOT_DIR / script_name
  subtests = (
    {
      'args':[],
      'input':'parse-align.in.txt',
      'outputs':{
        'ref':'parse-align.ref.fa',
        'fq1':'parse-align.reads_1.fq',
        'fq2':'parse-align.reads_2.fq'
      },
    },
    {
      'args':['--duplex'],
      'input':'parse-align.duplex.in.txt',
      'outputs':{
        'ref':'parse-align.duplex.ref.fa',
        'fq1':'parse-align.duplex.reads_1.fq',
        'fq2':'parse-align.duplex.reads_2.fq'
      },
    }
  )
  for data in subtests:
    print(f'{test_name} ::: {script_name} ::: {data["input"]}\t', end='')
    # $ parse-test-align.py [--duplex] parse-align.in.txt --ref parse-align.ref.fa \
    #   --fq1 parse-align.reads_1.fq --fq2 parse-align.reads_2.fq
    cmd = [script, TESTS_DIR/data['input']] + data['args']
    for key, outname in data['outputs'].items():
      cmd.append('--'+key)
      cmd.append(TESTS_DIR/(outname+'.tmp'))
    exitcode = run_command(cmd, onerror='stderr')
    if exitcode != 0:
      print('FAILED')
      continue
    failures = []
    for outname in data['outputs'].values():
      expected = TESTS_DIR/outname
      result = TESTS_DIR/(outname+'.tmp')
      if result.exists():
        stdout, exit_code = run_command_and_capture(('diff', expected, result))
        if stdout:
          failures.append((outname, head(stdout)))
        os.remove(result)
      else:
        logging.warning(f'Output file missing: {str(result)!r}')
    if failures:
      print('FAILED')
    else:
      print('success')
    for outname, diff in failures:
      print(f'  {outname}:')
      print(diff)


def get_context(test_name):
  script_name = 'getcontext.py'
  script = ROOT_DIR / script_name
  test_data = (
    {'inputs':('getcontext.in.fa', 'getcontext.in.tsv'), 'output':'getcontext.out.tsv'},
  )
  for data in test_data:
    input_ref, input_sites = data['inputs']
    output = data['output']
    print(f'{test_name} ::: {script_name} ::: {input_sites}\t', end='')
    cmd = (
      script, '--chrom-field', '1', '--coord-field', '2', '--window', '6',
      TESTS_DIR/input_ref, TESTS_DIR/input_sites
    )
    result, exit_code = run_command_and_capture(cmd, onerror='stderr')
    if exit_code != 0:
      print('FAILED')
    else:
      expected = read_file(TESTS_DIR/output)
      if result != expected:
        print('FAILED')
        for line in trimmed_diff(expected.splitlines(), result.splitlines()):
          print(line)
      else:
        print('success')


def trimmer(test_name):
  script_name = 'trimmer.py'
  script = ROOT_DIR / script_name
  test_data = (
    {
      'inputs': ('trimmer.in_1.fq', 'trimmer.in_2.fq'),
      'outputs': ('trimmer.out_1.fq', 'trimmer.out_2.fq'),
      'args': (
        '--format', 'fastq', '--filt-bases', 'ACGT', '--thres', '0.1', '--window', '10',
        '--invert', '--min-length', '10'
      ),
    },
  )
  for test in test_data:
    out1 = TESTS_DIR/'trimmer.out.tmp_1.fq'
    out2 = TESTS_DIR/'trimmer.out.tmp_2.fq'
    print(f'{test_name} ::: {script_name} ::: {test["inputs"][0]}/{test["inputs"][1]}\t', end='')
    input_paths = [TESTS_DIR/filename for filename in test['inputs']]
    cmd = (script, *test['args'], *input_paths, out1, out2)
    exit_code = run_command(cmd, onerror='stderr')
    if exit_code != 0:
      print('FAILED')
    else:
      diff_datas = []
      for expected_file, actual_file in zip(test['outputs'], (out1, out2)):
        expected = read_file(TESTS_DIR/expected_file)
        actual = read_file(TESTS_DIR/actual_file)
        if expected != actual:
          diff = trimmed_diff(expected.splitlines(), actual.splitlines())
          diff_datas.append({'diff':diff, 'expected':expected_file, 'actual':actual_file})
      if diff_datas:
        print('FAILED')
        for diff_data in diff_datas:
          print('{expected} vs {actual}:'.format(**diff_data))
          print('\n'.join(diff))
      else:
        print('success')
    cleanup(TESTS_DIR/out1, TESTS_DIR/out2)


GlobalsAfterActive = globals().copy()


##### Inactive tests #####

GlobalsAfterInactive = globals().copy()


##### Helper functions #####


def add_dicts(*dicts):
  combined = {}
  for d in dicts:
    for key, value in d.items():
      combined[key] = value
  return combined


def run_test_group(test_group):
  for test_name, test_fxn in test_group.items():
    test_fxn(test_name)


def get_objects_diff(objects_before, objects_after, object_type=types.FunctionType):
  diff = {}
  for name, obj in objects_after.items():
    if name not in objects_before and isinstance(obj, object_type):
      diff[name] = obj
  return diff


def head(string, lines=10):
  string_lines = string.splitlines()
  output = '\n'.join(string_lines[:lines])
  if len(string_lines) > lines:
    output += '\n\t...'
  return output


def run_command(command, onerror='warn'):
  if onerror == 'stderr':
    result = run_command_and_catch(command, onerror=onerror, stderr=subprocess.PIPE)
    if result.returncode != 0:
      logging.error(str(result.stderr, 'utf8'))
  else:
    result = run_command_and_catch(command, onerror=onerror, stderr=subprocess.DEVNULL)
  return result.returncode


def run_command_and_capture(command, onerror='warn'):
  result = run_command_and_catch(
    command, onerror=onerror, stdout=subprocess.PIPE, stderr=subprocess.PIPE
  )
  if result.returncode != 0 and onerror == 'stderr':
    logging.error(str(result.stderr, 'utf8'))
  return str(result.stdout, 'utf8'), result.returncode


def run_command_and_catch(command, onerror='warn', **kwargs):
  try:
    result = subprocess.run(command, **kwargs)
  except (OSError, subprocess.CalledProcessError) as error:
    if onerror == 'stderr':
      pass
    elif onerror == 'warn':
      logging.error(f'Error: ({type(error).__name__}) {error}')
    elif onerror == 'raise':
      raise
  return result


def read_file(path):
  try:
    with path.open('r') as file:
      return file.read()
  except OSError as error:
    logging.error(f'Error: {error}')
    return None


def trimmed_diff(lines1, lines2, lineterm=''):
  """Get a trimmed diff.
  Input lines should be newline-free."""
  diff_lines = difflib.unified_diff(lines1, lines2, n=1, fromfile='a', tofile='b',
                                    fromfiledate='c', tofiledate='d', lineterm=lineterm)
  header_line = 0
  for line in diff_lines:
    if header_line == 0 and line == '--- a\tc'+lineterm:
      header_line = 1
    elif header_line == 1 and line == '+++ b\td'+lineterm:
      header_line = 2
    elif header_line == 2:
      header_line = None
    if header_line is None:
      yield line


def cleanup(*paths):
  for path in paths:
    os.remove(path)


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass

#!/usr/bin/env python3
import argparse
import logging
import pathlib
import sys
try:
  from Bio.Align import PairwiseAligner
except ImportError:
  print(
    'Error importing Bio.Align.PairwiseAligner. Make sure BioPython is properly installed.',
    file=sys.stderr
  )
  raise
try:
  from Bio.Align import substitution_matrices
except ImportError:
  substitution_matrices = None
  print(
    'Error loading `Bio.Align.substitution_matrices`. Using shim instead. Install BioPython '
    '1.75 or later to use the native version.', file=sys.stderr
  )

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_MATRIX = SCRIPT_DIR/'sub-matrix.txt'
DEFAULT_GAP_OPEN = 0
DEFAULT_GAP_EXTEND = 2.5
DESCRIPTION = """Align two sequences with BioPython's PairwiseAligner."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('seq1')
  options.add_argument('seq2')
  options.add_argument('-m', '--matrix', type=pathlib.Path,
    help=f'Path to a substitution matrix file. Default: {DEFAULT_MATRIX}')
  options.add_argument('-s', '--scope', choices=('global','local'), default='local')
  options.add_argument('-o', '--gap-open', type=float, default=DEFAULT_GAP_OPEN,
    help='Gap open penalty. This will be subtracted from the alignment score at the start of each '
      'gap. Default: %(default)s')
  options.add_argument('-e', '--gap-extend', type=float, default=DEFAULT_GAP_EXTEND,
    help='Gap extension penalty. This will be subtracted from the alignment score for every base '
      'of the gap. Default: %(default)s')
  options.add_argument('-h', '--help', action='help',
    help='Print this argument help text and exit.')
  logs = parser.add_argument_group('Logging')
  logs.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = logs.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  if args.matrix:
    matrix_path = args.matrix
  else:
    matrix_path = DEFAULT_MATRIX

  alignment = align(
    args.seq1, args.seq2, scope=args.scope, gap_open=args.gap_open, gap_extend=args.gap_extend,
    matrix_file=matrix_path
  )
  print(alignment)


def align(seq1, seq2, **kwargs):
  aligner = Aligner(**kwargs)
  return aligner.align(seq1, seq2)


class Aligner:
  def __init__(
    self, scope='local', gap_open=DEFAULT_GAP_OPEN, gap_extend=DEFAULT_GAP_EXTEND,
    matrix_file=DEFAULT_MATRIX, matrix=None
  ):
    if matrix is None:
      if not matrix_file:
        raise RuntimeError(f'Must give either a `matrix` or `matrix_file` to {type(self).__name__}')
      if substitution_matrices is None:
        matrix = substitution_matrix_loader(matrix_file)
      else:
        matrix = substitution_matrices.read(matrix_file)
    self._aligner = PairwiseAligner()
    self._aligner.mode = scope
    # The gap penalty values are actually *added* to the alignment score, so if you're using the
    # intuitive sense of the term "penalty" (a value to be subtracted from the score), you have to
    # negate it.
    # Also, BioPython takes `open_gap_score` to mean the entirety of the penalty applied to the
    # first base of the gap. The `extend_gap_score` will be applied to subsequent bases, but not the
    # first base. So if you're using the more common definitions of "gap open" and "gap extension"
    # penalties, the `open_gap_score` must be the sum of your gap open and gap extension penalties.
    # See https://biopython.readthedocs.io/en/latest/chapter_align.html#affine-gap-scores for where
    # they define how they use the values.
    self._aligner.open_gap_score = -(gap_open + gap_extend)
    self._aligner.extend_gap_score = -gap_extend
    self._aligner.substitution_matrix = matrix

  @property
  def algorithm(self):
    return self._aligner.algorithm
  
  def align(self, seq1, seq2):
    alignments = self._aligner.align(seq1, seq2)
    if len(alignments) > 0:
      return Alignment(alignments[0])
    else:
      return None

  def aligns(self, seq1, seq2):
    alignments = self._aligner.align(seq1, seq2)
    return (Alignment(aln) for aln in alignments)


class Alignment:
  def __init__(self, alignment):
    self.target, self.matches_str, self.query = str(alignment).splitlines()
    self.score = alignment.score

  def __str__(self):
    """Print a human-readable representation of the alignment."""
    return '\n'.join((self.target, self.matches_str, self.query))


def substitution_matrix_loader(matrix_path):
  x_bases = None
  matrix = {}
  with matrix_path.open() as matrix_file:
    for line_num, line_raw in enumerate(matrix_file,1):
      line = line_raw.strip()
      if line.startswith('#'):
        continue
      if x_bases is None:
        x_bases = line.split()
        continue
      y_base, *score_strs = line.split()
      scores = [float(s) for s in score_strs]
      if len(scores) != len(x_bases):
        raise ValueError(
          f'Line {line_num} has {len(scores)} scores but the header has {len(x_bases)} bases.'
        )
      for x_base, score in zip(x_bases, scores):
        matrix[(x_base,y_base)] = score
  return matrix


def fail(message):
  logging.critical(f'Error: {message}')
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception(message)


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass

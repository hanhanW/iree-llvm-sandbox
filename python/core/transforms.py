from mlir.ir import *

from .search_vars import *
from .transform import Transform, TransformationList

import mlir.all_passes_registration


def _get_tile_sizes_str(transform: Transform) -> str:
  """Compute the textual tile size flag for the given `transform`."""
  if not transform.tile_sizes:
    return ''
  return f'tile-sizes={",".join([str(ts) for ts in transform.tile_sizes])}'


def _get_tile_interchange_str(transform: Transform) -> str:
  """Compute the textual tile interchange flag for the given `transform`."""
  if not transform.tile_interchange:
    return ''
  tile_interchange = [str(ti) for ti in transform.tile_interchange]
  return f'tile-interchange={",".join(tile_interchange)}'


def _get_pad_str(transform: Transform) -> str:
  """Compute the textual padding flags for the given `transform`."""
  if not transform.pad:
    return ''
  pad_str = f'pad'
  pack_paddings = [str(pp) for pp in transform.pack_paddings]
  hoist_paddings = [str(hd) for hd in transform.hoist_paddings]
  if pack_paddings:
    pad_str = pad_str + f' pack-paddings={",".join(pack_paddings)}'
  if hoist_paddings:
    pad_str = pad_str + f' hoist-paddings={",".join(hoist_paddings)}'
  return pad_str


class ExperimentalSplitAndFuseFillOp(Transform):
  """Tile and fuse FillOp into the output of reduction.

  This transform can be configured as follows:
  * `tile_sizes`: Tile sizes used for tiling.
  """

  def __init__(self, fun_name: str, op_name: str, tile_sizes=[], **kwargs):
    if tile_sizes:
      tile_str = f'tile-sizes={",".join([str(ts) for ts in tile_sizes])}'
    pipeline = (f'linalg-fuse-fill-into-reduction{{'
                f'     anchor-func={fun_name} '
                f'     anchor-op={op_name} '
                f'     {tile_str}}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = (f'builtin.func({pipeline})')


class Inject(Transform):
  """Inject intermediate IR.

  Replace the module by the provided IR. The transform can be configured as
  follows:
  * `ir_to_inject`: Textual IR to inject.
  """

  def __init__(self, ir_to_inject: str, **kwargs):
    self.ir_to_inject = ir_to_inject

  def __call__(self, module: Module, fun_name: str, **kwargs):
    return Module.parse(self.ir_to_inject)


class Fuse(Transform):
  """Tile a linalg op and fuse its producers.

  This transform can be configured as follows:
  * `tile_sizes`: Tile sizes used for tiling.
  * `tile_interchange`: Interchange used for tiling.
  * `pad`: Pad the operands.
  * `pack_paddings`: Pack the padded operand if the packing flag is set. `pad`
     must also be specified.
  * `hoist_paddings`: Hoist the padded operand by the specified number of loops.
     pad` must also be specified.
  * `vectorize`: Vectorize the fused operations.
  * `vectorize_padding`: Vectorize the pad tensor operations.
  """

  variables = {
      'tile_sizes': TilingSizesVariable,
      'tile_interchange': InterchangeVariable,
      'pad': BoolVariable,
      'pack_paddings': PackPaddingVariable,
      'hoist_paddings': HoistPaddingVariable,
      'vectorize': BoolVariable,
      'vectorize_paddings': BoolVariable,
  }

  def __init__(self, fun_name: str, op_name: str, **kwargs):
    self._parse_variables_in_kwargs(kwargs, {
        'tile_sizes': [],
        'tile_interchange': [],
        'pad': False,
        'pack_paddings': [],
        'hoist_paddings': [],
        'vectorize': False,
        'vectorize_paddings': False,
    })
    tile_str = _get_tile_sizes_str(self)
    interchange_str = _get_tile_interchange_str(self)
    pad_str = _get_pad_str(self)
    vectorize_str = ''
    if self.vectorize:
      vectorize_str = f'vectorize'
      if self.vectorize_paddings:
        vectorize_str = vectorize_str + f' vectorize-padding'
    pipeline = (f'linalg-fuse{{'
                f'     anchor-func={fun_name} '
                f'     anchor-op={op_name} '
                f'     {tile_str} '
                f'     {interchange_str} '
                f'     {pad_str} '
                f'     {vectorize_str}}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = (f'builtin.func({pipeline})')


class Tile(Transform):
  """Tile a linalg op with `tile_sizes`.

  This transform can be configured as follows:
  * `tile_sizes`: Tile sizes used for tiling.
  * `tile_interchange`: Interchange used for tiling.
  * `peel`: Peel the specified loops generated by the tiling pattern. Cannot be
     used together with `pad`.
  * `pad`: Pad the operands.
  * `pack_paddings`: Pack the padded operand if the packing flag is set. `pad`
     must also be specified.
  * `hoist_paddings`: Hoist the padded operand by the specified number of loops.
     pad` must also be specified.
  * `scalarize_dyn_dims`: Scalarize all dimensions that having statically
    unknown size. Either `tile_sizes` or `scalarize_dyn_dims` must be specified.
    Cannot use both at the same time. Cannot be used together with `pad` or
    `peel`.
  """

  variables = {
      'tile_sizes': TilingSizesVariable,
      'tile_interchange': InterchangeVariable,
      'pad': BoolVariable,
      'peel': PeelingVariable,
      'pack_paddings': PackPaddingVariable,
      'hoist_paddings': HoistPaddingVariable,
  }

  def __init__(
      self,
      fun_name: str,
      op_name: str,
      # TODO: move this to a tunable variable.
      scalarize_dyn_dims=False,
      **kwargs):
    self._parse_variables_in_kwargs(
        kwargs, {
            'tile_sizes': [],
            'tile_interchange': [],
            'pad': False,
            'peel': [],
            'pack_paddings': [],
            'hoist_paddings': []
        })
    tile_str = _get_tile_sizes_str(self)
    interchange_str = _get_tile_interchange_str(self)
    pad_str = _get_pad_str(self)
    peeled_loops_str = ''
    scalarize_dyn_dims_str = ''
    if self.peel:
      loop_indices = [str(l) for l in self.peel]
      peeled_loops_str = f'peeled-loops={",".join(loop_indices)}'
    if scalarize_dyn_dims:
      scalarize_dyn_dims_str = 'scalarize-dynamic-dims'

    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'     anchor-func={fun_name} '
                f'     anchor-op={op_name} '
                f'     {tile_str} '
                f'     {interchange_str} '
                f'     {peeled_loops_str} '
                f'     {scalarize_dyn_dims_str} '
                f'     {pad_str}}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = (f'builtin.func({pipeline})')


class Vectorize(Transform):

  def __init__(self, fun_name: str, op_name: str, **kwargs):
    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'     anchor-func={fun_name} '
                f'     anchor-op={op_name} '
                f'     vectorize '
                f'     vectorize-padding}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = (f'builtin.func({pipeline})')


class Generalize(Transform):
  """Transform a named operation to its generic form.

  This transform can be configured as follows:
  * `iterator_interchange`: Interchange the iterators of the generic operation.

  Note: After generalization the anchor op name changes to 'linalg.generic'.
  """

  variables = {
      'iterator_interchange': InterchangeVariable,
  }

  def __init__(self, fun_name: str, op_name: str, **kwargs):
    self._parse_variables_in_kwargs(kwargs, {'iterator_interchange': []})
    interchange_str = ''

    if self.iterator_interchange:
      dims = [str(ic) for ic in self.iterator_interchange]
      interchange_str = f'iterator-interchange={",".join(dims)}'

    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'     anchor-func={fun_name} '
                f'     anchor-op={op_name} '
                f'     generalize '
                f'     {interchange_str}}}')
    self.pipeline = (f'builtin.func({pipeline})')


class DecomposeToLowerDimensionalNamedOp(Transform):
  """Rewrite all known named ops to a lower-dimensional form suitable for

     vectorization.

    TODO: atm this is applied to all supported ops. If/when we need finer
    control this should be exposed with an opName + filter and a proper
    pattern.
  """

  def __init__(self, **kwargs):
    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'     decompose-to-lower-dim }}')
    self.pipeline = (f'builtin.func({pipeline})')


class Bufferize(Transform):

  def __init__(self, **kwargs):
    pipeline = (f'linalg-bufferization-driver,' f'canonicalize,' f'cse')
    self.pipeline = pipeline


class LowerVectors(Transform):

  def __init__(self, stage, **kwargs):
    contraction_lowering = 'outerproduct' if 'contraction_lowering' not in \
        kwargs else kwargs['contraction_lowering']
    multi_reduction_lowering = 'innerparallel' if 'multi_reduction_lowering' \
        not in kwargs else kwargs['multi_reduction_lowering']
    transpose_lowering = 'eltwise' if 'transpose_lowering' not in \
        kwargs else kwargs['transpose_lowering']
    transpose_avx2_lowering = False if ('transpose_avx2_lowering' not in \
        kwargs or not kwargs['transpose_lowering']) else True
    pipeline = (
        f'linalg-vector-lowering{{'
        f'    lower-vector-stage={stage}'
        f'    max-transfer-rank=1 '
        f'    split-transfers=linalg-copy '
        f'    lower-vector-transpose-to={transpose_lowering} '
        f'    lower-vector-transpose-to-avx2={transpose_avx2_lowering} '
        f'    lower-vector-multi-reduction-to={multi_reduction_lowering} '
        f'    lower-vector-contraction-to={contraction_lowering} '
        f'    unroll-vector-transfers=true}},'
        f'canonicalize,'
        f'cse')
    self.pipeline = (f'builtin.func({pipeline})')

def StagedVectorLowering(**kwargs):
  return TransformationList(
      transforms=[LowerVectors(stage=i, **kwargs) for i in range(7)])


class LowerToLLVM(Transform):

  def __init__(self, **kwargs):
    pipeline = (f'llvm-lowering,' f'canonicalize,' f'cse')
    self.pipeline = pipeline


class Sparsify(Transform):

  def __init__(self, options: str):
    pipeline = (
        f'sparsification{{{options}}},'
        f'sparse-tensor-conversion,'
        f'builtin.func(convert-linalg-to-loops,convert-vector-to-scf),'
        f'convert-scf-to-std,'
        f'func-bufferize,'
        f'tensor-constant-bufferize,'
        f'builtin.func(tensor-bufferize,std-bufferize,finalizing-bufferize),'
        f'convert-vector-to-llvm{{reassociate-fp-reductions=1 enable-index-optimizations=1}},'
        f'lower-affine,'
        f'convert-memref-to-llvm,'
        f'convert-std-to-llvm,'
        f'reconcile-unrealized-casts')
    self.pipeline = pipeline

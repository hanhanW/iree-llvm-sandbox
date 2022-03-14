# RUN: %PYTHON %s 2>&1 | FileCheck %s

# This file contains small benchmarks with reasonably-sized problem/tiling sizes
# and codegen options.

from ..core.experts import *
from ..core.harness import *
from ..core.transforms import *

from ..contraction.definitions import EinsumProblem

fun_name = 'matmul'
op_name = 'linalg.generic'

################################################################################
### Compilation strategies.
################################################################################

# Note: `\` char at the end of next line prevents formatter reflows, keep it.
all_names = [                    \
  "SingleTiling2DPeel",          \
  "SingleTiling3DPeel",          \
  "SingleTiling3DPad",           \
  "SingleTiling3DPeelTranspose", \
  "DoubleTile2DPadAndHoist",     \
]


def all_experts(fun_name):
  return [
    # Note: `\` char at the end of next line prevents formatter reflows, keep it.
    e.print_ir(after_all=True, at_begin=True, llvm=False) for e in [ \
        Tile(fun_name,
             op_name,
             tile_sizes=[6, 32, 1],
             tile_interchange=[0, 1, 2],
             peel=[0, 1, 2])
          .then(Vectorize(fun_name, ''))
          .then(LoweringOnlyExpert(fun_name, op_name)),
        Tile(fun_name,
             op_name,
             tile_sizes=[12, 32, 16],
             tile_interchange=[0, 1, 2],
             peel=[0, 1, 2])
          .then(Vectorize(fun_name, ''))
          .then(LoweringOnlyExpert(fun_name, op_name)),
        Tile(fun_name,
             op_name,
             tile_sizes=[12, 32, 16],
             tile_interchange=[0, 1, 2],
             pad=True,
             pack_paddings=[1, 1, 0],
             hoist_paddings=[2, 3, 0])
          .then(Vectorize(fun_name, ''))
          .then(LoweringOnlyExpert(fun_name, op_name)),
        Tile(fun_name,
             op_name,
             tile_sizes=[6, 32, 16],
             tile_interchange=[2, 1, 0],
             peel=[0, 1, 2],
             )
          .then(Vectorize(fun_name, ''))
          .then(LoweringOnlyExpert(fun_name, op_name,
                                   transpose_lowering='shuffle')),
        DoubleTile(fun_name,
                   op_name,
                   tile_sizes1=[288, 128, 512],
                   tile_interchange1=[0, 2, 1],
                   tile_sizes2=[12, 32, 1],
                   tile_interchange2=[0, 1, 2],
                   pad2=True,
                   pack_paddings2=[1, 1, 0],
                   hoist_paddings2=[5, 6, 0],
                   transpose_paddings2=[[1, 0], [0, 1], [0, 1]],
                   )
          .then(Vectorize(fun_name, ''))
          .then(UnrollOneParentLoop(fun_name,
                                    'vector.contract',
                                    parent_loop_num=1,
                                    unroll_factor=4))
          .then(LoweringOnlyExpert(fun_name,
                                   op_name,
                                   transpose_lowering='eltwise')),
    ]
  ]


################################################################################
### Problem instantiations.
################################################################################

keys = ['m', 'n', 'k']


# CHECK-NOT: FAILURE
def main():
  # Specify default configuration and parse command line.
  args = test_argparser(
      "matmul benchmark",
      default_n_iters=100,
      default_problem_sizes_list=[ \
        [4, 16, 8]],
      default_expert_list=all_names,
      default_dynamic_at_compile_time_list=[
          [],  # case 1: static at compile time
          ['m', 'k'],  # case 2: partially dynamic at compile time
          keys  # case 3: fully dynamic at compile time
      ],
      default_spec_list=[
          # 'km,kn',  # C += A^T.B  fastest
          'mk,kn',  # C += A.B
          # 'mk,nk'  # C += A.B^T  slowest
      ])

  for dynamic_at_compile_time in args.dynamic_at_compile_time_list:
    for spec in args.spec_list:

      def numpy_kernel(args, sizes, types):
        A, B, C = args
        C.fill(0.)
        if spec == 'km,kn':
          A = np.transpose(A)
        if spec == 'mk,nk':
          B = np.transpose(B)
        np.dot(A, B, out=C)

      def pytorch_kernel(args, sizes, types):
        import torch
        A, B, C = args
        C.fill_(0.)
        if spec == 'km,kn':
          A = np.transpose(A)
        if spec == 'mk,nk':
          B = np.transpose(B)
        torch.mm(A, B, out=C)

      func_with_spec = fun_name + '_' + spec
      func_with_spec = func_with_spec.replace(',', '')

      test_harness(lambda s, t: EinsumProblem(spec, 'mnk', 2),
                   [[np.float32] * 3],
                   test_sizes(keys, args.problem_sizes_list),
                   test_experts(all_experts(func_with_spec), all_names,
                                args.expert_list),
                   n_iters=args.n_iters,
                   dynamic_at_compile_time_sizes=set(
                       dynamic_at_compile_time).intersection(keys),
                   function_name=func_with_spec,
                   dump_ir_to_file='/tmp/abc.mlir',
                   dump_obj_to_file='/tmp/abc.o',
                   dump_data_to_file=args.dump_data,
                   numpy_benchmark=numpy_kernel,
                   pytorch_benchmark=pytorch_kernel,
                   backends=['strategy'],
                   zero_at_each_iteration = True)


if __name__ == '__main__':
  main()

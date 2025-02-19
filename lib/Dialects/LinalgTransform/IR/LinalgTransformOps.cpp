//===-- LinalgTransformOps.cpp - Linalg Transform dialect -----------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "Dialects/LinalgTransform/LinalgTransformOps.h"
#include "mlir/IR/Builders.h"
#include "mlir/IR/Diagnostics.h"
#include "mlir/IR/OpImplementation.h"
#include "mlir/Transforms/InliningUtils.h"
#include "llvm/ADT/STLExtras.h"

#include "Dialects/LinalgTransform/LinalgTransformOpsDialect.cpp.inc"

using namespace mlir;
using namespace mlir::linalg;

void transform::LinalgTransformDialect::initialize() {
  addOperations<
#define GET_OP_LIST
#include "Dialects/LinalgTransform/LinalgTransformOps.cpp.inc"
      >();
}

void transform::ScopeOp::getSuccessorRegions(
    Optional<unsigned> index, ArrayRef<Attribute> operands,
    SmallVectorImpl<RegionSuccessor> &regions) {
  if (index)
    regions.emplace_back(getResults());
  else
    regions.emplace_back(&body());
}

static LogicalResult verifySequenceOp(transform::SequenceOp op) {
  WalkResult result = op.walk([](Operation *child) {
    for (OpResult result : child->getResults()) {
      if (llvm::hasNItemsOrLess(result.getUses(), 1))
        continue;
      InFlightDiagnostic diag = child->emitError()
                                << "result #" << result.getResultNumber()
                                << " has more than one use";
      for (OpOperand &use : result.getUses()) {
        diag.attachNote(use.getOwner()->getLoc())
            << "used here as operand #" << use.getOperandNumber();
      }
      return WalkResult::interrupt();
    }
    return WalkResult::advance();
  });
  return failure(result.wasInterrupted());
}

#define GET_OP_CLASSES
#include "Dialects/LinalgTransform/LinalgTransformOps.cpp.inc"

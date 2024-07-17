import os
os.environ['FLAGS_cinn_new_group_scheduler'] = '1'
os.environ['FLAGS_group_schedule_tiling_first'] = '1'
os.environ['FLAGS_enable_pir_api'] = '1'
os.environ['FLAGS_cinn_bucket_compile'] = '1'
import sys
import unittest
import numpy as np
from dataclasses import dataclass
import typing as t

@dataclass
class Stage:
    name: str
    env_vars: t.Dict[str, str]

cinn_stages = [
    Stage(
        name="dynamic_to_static",
        env_vars=dict(
            PADDLE_DEBUG_ENABLE_CINN=False,
            FLAGS_prim_all=False,
            FLAGS_prim_enable_dynamic=False,
        ),
    ),
    Stage(
        name="prim",
        env_vars=dict(
            PADDLE_DEBUG_ENABLE_CINN=False,
            FLAGS_prim_all=True,
            FLAGS_prim_enable_dynamic=True,
        ),
    ),
    Stage(
        name="infer_symbolic",
        env_vars=dict(
            PADDLE_DEBUG_ENABLE_CINN=False,
            FLAGS_prim_all=True,
            FLAGS_prim_enable_dynamic=True,
            FLAGS_use_cinn=False,
            FLAGS_check_infer_symbolic=True,
        ),
    ),
	Stage(
        name="frontend",
        env_vars=dict(
            PADDLE_DEBUG_ENABLE_CINN=True,
            FLAGS_prim_all=True,
            FLAGS_prim_enable_dynamic=True,
            FLAGS_use_cinn=True,
            FLAGS_check_infer_symbolic=False,
            FLAGS_enable_fusion_fallback=True,
        ), 
    ),
    Stage(
        name="backend",
        env_vars=dict(
            PADDLE_DEBUG_ENABLE_CINN=True,
            FLAGS_prim_all=True,
            FLAGS_prim_enable_dynamic=True,
            FLAGS_use_cinn=True,
            FLAGS_check_infer_symbolic=False,
            FLAGS_enable_fusion_fallback=False,
        ), 
    ),
]

def GetCinnStageByName(name):
    for stage in cinn_stages:
        if stage.name == name:
            return stage
    return None

def GetCurrentCinnStage():
    name = os.getenv('PADDLE_DEBUG_CINN_STAGE_NAME')
    if name is None:
        return None
    stage_names = [stage.name for stage in cinn_stages]
    assert name in stage_names, (
        f"PADDLE_DEBUG_CINN_STAGE_NAME should be in {stage_names}"
    )
    return GetCinnStageByName(name)

def GetPrevCinnStage(stage):
    for i in range(1, len(cinn_stages)):
        if stage is cinn_stages[i]:
            return cinn_stages[i - 1]
    return None

def IsCinnStageEnableDiff():
    value = os.getenv('PADDLE_DEBUG_CINN_STAGE_ENABLE_DIFF')
    enabled = value in {
        '1',
        'true',
        'True',
    }
    if enabled:
        assert GetCurrentCinnStage() is not None
    return enabled

def GetExitCodeAndStdErr(cmd, env):
    env = {
        k:v
        for k, v in env.items()
        if v is not None
    }
    import subprocess
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    return result.returncode, result.stderr

def GetStageExitCodeAndStdErr(stage):
    return GetExitCodeAndStdErr(
        [sys.executable, __file__],
        env=dict(
            PADDLE_DEBUG_CINN_STAGE_NAME=stage.name,
            PADDLE_DEBUG_CINN_STAGE_ENABLE_DIFF='0',
            PYTHONPATH=os.getenv('PYTHONPATH'),
            ATHENA_ENABLE_TRY_RUN="False",
        ),
    )

def AthenaTryRunEnabled():
    return os.getenv('ATHENA_ENABLE_TRY_RUN') not in {
        "0",
        "False",
        "false",
        "OFF"
    }

def GetNeedSkipAndSkipMessage():
    current_stage = GetCurrentCinnStage()
    assert current_stage is not None
    if not IsCinnStageEnableDiff():
        return False, ""
    last_stage = GetPrevCinnStage(current_stage)
    if last_stage is None:
        return False, ""
    exitcode, stderr = GetStageExitCodeAndStdErr(last_stage)
    if exitcode != 0:
        return True, f"last stage failed."
    return False, ""

def GetCurrentStageTryRunExitCodeAndStdErr():
    if not AthenaTryRunEnabled():
        return False, ""
    current_stage = GetCurrentCinnStage()
    assert current_stage is not None
    return GetStageExitCodeAndStdErr(current_stage)

def SetDefaultEnv(**env_var2value):
    for env_var, value in env_var2value.items():
        if os.getenv(env_var) is None:
            os.environ[env_var] = str(value)

SetDefaultEnv(
    PADDLE_DEBUG_CINN_STAGE_NAME="backend",
    PADDLE_DEBUG_CINN_STAGE_ENABLE_DIFF=False,
    PADDLE_DEBUG_ENABLE_CINN=True,
    FLAGS_enable_pir_api=True,
    FLAGS_prim_all=True,
    FLAGS_prim_enable_dynamic=True,
    FLAGS_use_cinn=False,
    FLAGS_check_infer_symbolic=False,
    FLAGS_enable_fusion_fallback=False,
)

need_skip, skip_message = GetNeedSkipAndSkipMessage()
try_run_exit_code, try_run_stderr = GetCurrentStageTryRunExitCodeAndStdErr()
class TestTryRun(unittest.TestCase):
    def test_panic(self):
        if not AthenaTryRunEnabled():
            return
        if try_run_exit_code == 0:
            # All unittest cases passed.
            return
        if try_run_exit_code > 0:
            # program failed but not panic.
            return
        # program panicked.
        kOutputLimit = 65536
        message = try_run_stderr[-kOutputLimit:]
        raise RuntimeError(f"panicked. last {kOutputLimit} characters of stderr: \n{message}")

import paddle

def SetEnvVar(env_var2value):
    for env_var, value in env_var2value.items():
        os.environ[env_var] = str(value)
    paddle.set_flags({
        env_var:value
        for env_var, value in env_var2value.items()
        if env_var.startswith('FLAGS_')
    })

if GetCurrentCinnStage() is not None:
    SetEnvVar(GetCurrentCinnStage().env_vars)

def NumOperationsInBlock(block_idx):
    return [53][block_idx] - 1 # number-of-ops-in-block

def GetPaddleDebugNumAllowedOps():
    try:
        return int(os.getenv('PADDLE_DEBUG_NUM_ALLOWED_OPS'))
    except:
        return None

paddle_debug_num_allowed_ops = GetPaddleDebugNumAllowedOps()


if type(paddle_debug_num_allowed_ops) is not int:
    def EarlyReturn(block_idx, op_idx):
        return False      
else:
    def EarlyReturn(block_idx, op_idx):
        return op_idx >= paddle_debug_num_allowed_ops

class BlockEntries:

    def builtin_module_201_0_0(self, data_1, data_2, data_0):

        # pd_op.full: (1xi32) <- ()
        full_0 = paddle._C_ops.full([1], float('2'), paddle.int32, paddle.core.CPUPlace())

        # pd_op.assign: (1xi32) <- (1xi32)
        assign_0 = full_0

        # pd_op.split_with_num: ([-1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32]) <- (-1x-1x-1x-1xf32, 1xi32)
        split_with_num_0 = paddle._C_ops.split_with_num(data_0, 4, full_0)

        # builtin.split: (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32) <- ([-1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32])
        split_0, split_1, split_2, split_3, = split_with_num_0

        # pd_op.full_int_array: (1xi64) <- ()
        full_int_array_0 = [0]

        # pd_op.unsqueeze: (1x-1x-1x-1xf32, 0x-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xi64)
        unsqueeze_0, unsqueeze_1 = (lambda x, f: f(x))(paddle._C_ops.unsqueeze(data_1, full_int_array_0), lambda out: out if isinstance(out, (list, tuple)) else (out, None))

        # pd_op.subtract: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        subtract_0 = split_1 - split_0

        # pd_op.subtract: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        subtract_1 = split_3 - split_0

        # pd_op.full_int_array: (3xi64) <- ()
        full_int_array_1 = [2, 2, 1]

        # pd_op.split: ([-1x-1x-1xf32, -1x-1x-1xf32, -1x-1x-1xf32]) <- (-1x-1x-1xf32, 3xi64, 1xi32)
        split_4 = paddle._C_ops.split(data_2, full_int_array_1, assign_0)

        # builtin.split: (-1x-1x-1xf32, -1x-1x-1xf32, -1x-1x-1xf32) <- ([-1x-1x-1xf32, -1x-1x-1xf32, -1x-1x-1xf32])
        split_5, split_6, split_7, = split_4

        # pd_op.full_int_array: (1xi64) <- ()
        full_int_array_2 = [2]

        # pd_op.unsqueeze: (-1x-1x1x-1xf32, 0x-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xi64)
        unsqueeze_2, unsqueeze_3 = (lambda x, f: f(x))(paddle._C_ops.unsqueeze(split_5, full_int_array_2), lambda out: out if isinstance(out, (list, tuple)) else (out, None))

        # pd_op.subtract: (-1x-1x-1x-1xf32) <- (1x-1x-1x-1xf32, -1x-1x1x-1xf32)
        subtract_2 = unsqueeze_0 - unsqueeze_2

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_0 = subtract_2 * subtract_0

        # pd_op.full_int_array: (1xi64) <- ()
        full_int_array_3 = [-1]

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_1 = full_int_array_3

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_2 = full_int_array_3

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_3 = full_int_array_3

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_4 = full_int_array_3

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_0 = paddle._C_ops.sum(multiply_0, full_int_array_3, None, False)

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_1 = subtract_2 * subtract_1

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_1 = paddle._C_ops.sum(multiply_1, assign_4, None, False)

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_2 = subtract_0 * subtract_0

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_2 = paddle._C_ops.sum(multiply_2, assign_3, None, False)

        # pd_op.sqrt: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        sqrt_0 = paddle.sqrt(sum_2)

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_3 = subtract_1 * subtract_1

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_3 = paddle._C_ops.sum(multiply_3, assign_2, None, False)

        # pd_op.sqrt: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        sqrt_1 = paddle.sqrt(sum_3)

        # pd_op.min: (-1x-1x1xf32) <- (-1x-1x-1xf32, 1xi64)
        min_0 = paddle._C_ops.min(split_6, assign_1, True)

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_0 = paddle._C_ops.pow(sum_0, float('2'))

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_1 = paddle._C_ops.pow(sqrt_0, float('3'))

        # pd_op.multiply: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x1xf32)
        multiply_4 = pow_1 * min_0

        # pd_op.full: (1xf32) <- ()
        full_1 = paddle._C_ops.full([1], float('1'), paddle.float32, paddle.core.CPUPlace())

        # pd_op.assign: (1xf32) <- (1xf32)
        assign_5 = full_1

        # pd_op.assign: (1xf32) <- (1xf32)
        assign_6 = full_1

        # pd_op.scale: (-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xf32)
        scale_0 = paddle._C_ops.scale(multiply_4, full_1, float('1e-09'), True)

        # pd_op.divide: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x-1xf32)
        divide_0 = pow_0 / scale_0

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_2 = paddle._C_ops.pow(sum_1, float('2'))

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_3 = paddle._C_ops.pow(sqrt_1, float('3'))

        # pd_op.multiply: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x1xf32)
        multiply_5 = pow_3 * min_0

        # pd_op.scale: (-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xf32)
        scale_1 = paddle._C_ops.scale(multiply_5, assign_6, float('1e-09'), True)

        # pd_op.divide: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x-1xf32)
        divide_1 = pow_2 / scale_1

        # pd_op.add: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x-1xf32)
        add_0 = divide_0 + divide_1

        # pd_op.full: (1xf32) <- ()
        full_2 = paddle._C_ops.full([1], float('-6'), paddle.float32, paddle.core.CPUPlace())

        # pd_op.scale: (-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xf32)
        scale_2 = paddle._C_ops.scale(add_0, full_2, float('0'), True)

        # pd_op.exp: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        exp_0 = paddle._C_ops.exp(scale_2)

        # pd_op.full: (1xf32) <- ()
        full_3 = paddle._C_ops.full([1], float('0.0833333'), paddle.float32, paddle.core.CPUPlace())

        # pd_op.scale: (-1x-1x1xf32) <- (-1x-1x1xf32, 1xf32)
        scale_3 = paddle._C_ops.scale(min_0, full_3, float('0'), True)

        # pd_op.full: (1xf32) <- ()
        full_4 = paddle._C_ops.full([1], float('6.28319'), paddle.float32, paddle.core.CPUPlace())

        # pd_op.scale: (-1x-1x1xf32) <- (-1x-1x1xf32, 1xf32)
        scale_4 = paddle._C_ops.scale(scale_3, full_4, float('0'), True)

        # pd_op.scale: (-1x-1x1xf32) <- (-1x-1x1xf32, 1xf32)
        scale_5 = paddle._C_ops.scale(scale_4, assign_5, float('1e-09'), True)

        # pd_op.divide: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x1xf32)
        divide_2 = exp_0 / scale_5
        return full_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, assign_0, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, sum_0, multiply_1, assign_4, sum_1, multiply_2, assign_3, sqrt_0, multiply_3, assign_2, sqrt_1, assign_1, min_0, pow_0, pow_1, full_1, scale_0, divide_0, pow_2, pow_3, assign_6, scale_1, divide_1, full_2, full_3, full_4, assign_5, scale_5, exp_0, divide_2



def GetEnvVarEnableJit():
    enable_jit = os.getenv('PADDLE_DEBUG_ENABLE_JIT')
    return enable_jit not in {
        "0",
        "False",
        "false",
        "OFF",
    }

def GetEnvVarEnableCinn():
    enable_cinn = os.getenv('PADDLE_DEBUG_ENABLE_CINN')
    return enable_cinn not in {
        "0",
        "False",
        "false",
        "OFF",
    }


def GetTolerance(dtype):
    if dtype == np.float16:
        return GetFloat16Tolerance()
    if dtype == np.float32:
        return GetFloat32Tolerance()
    return 1e-6

def GetFloat16Tolerance():
    try:
        return float(os.getenv('PADDLE_DEBUG_FLOAT16_TOL'))
    except:
        return 1e-3

def GetFloat32Tolerance():
    try:
        return float(os.getenv('PADDLE_DEBUG_FLOAT32_TOL'))
    except:
        return 1e-6

def IsInteger(dtype):
    return np.dtype(dtype).char in np.typecodes['AllInteger']


class CinnTestBase:
    def setUp(self):
        paddle.seed(2024)
        self.prepare_data()

    def _test_entry(self):
        dy_outs = self.entry(use_cinn=False)
        cinn_outs = self.entry(use_cinn=GetEnvVarEnableCinn())

        for cinn_out, dy_out in zip(cinn_outs, dy_outs):
          if type(cinn_out) is list and type(dy_out) is list:
            for x, y in zip(cinn_out, dy_out):
              self.assert_all_close(x, y)
          else:
            self.assert_all_close(cinn_out, dy_out)

    def assert_all_close(self, x, y):
        if (hasattr(x, "numpy") and hasattr(y, "numpy")):
            x_numpy = x.numpy()
            y_numpy = y.numpy()
            assert x_numpy.dtype == y_numpy.dtype
            if IsInteger(x_numpy.dtype):
                np.testing.assert_equal(x_numpy, y_numpy)
            else:
                tol = GetTolerance(x_numpy.dtype)
                np.testing.assert_allclose(x_numpy, y_numpy, atol=tol, rtol=tol)
        else:
            assert x == y

class Block_builtin_module_201_0_0(paddle.nn.Layer, BlockEntries):
    def __init__(self):
        super().__init__()

    def forward(self, data_1, data_2, data_0):
        args = [data_1, data_2, data_0]
        for op_idx, op_func in enumerate(self.get_op_funcs()):
            if EarlyReturn(0, op_idx):
                return args
            args = op_func(*args)
        return args

    def get_op_funcs(self):
        return [
            self.op_full_0,
            self.op_assign_0,
            self.op_split_with_num_0,
            self.op_split_0,
            self.op_full_int_array_0,
            self.op_unsqueeze_0,
            self.op_subtract_0,
            self.op_subtract_1,
            self.op_full_int_array_1,
            self.op_split_1,
            self.op_split_2,
            self.op_full_int_array_2,
            self.op_unsqueeze_1,
            self.op_subtract_2,
            self.op_multiply_0,
            self.op_full_int_array_3,
            self.op_assign_1,
            self.op_assign_2,
            self.op_assign_3,
            self.op_assign_4,
            self.op_sum_0,
            self.op_multiply_1,
            self.op_sum_1,
            self.op_multiply_2,
            self.op_sum_2,
            self.op_sqrt_0,
            self.op_multiply_3,
            self.op_sum_3,
            self.op_sqrt_1,
            self.op_min_0,
            self.op_pow_0,
            self.op_pow_1,
            self.op_multiply_4,
            self.op_full_1,
            self.op_assign_5,
            self.op_assign_6,
            self.op_scale_0,
            self.op_divide_0,
            self.op_pow_2,
            self.op_pow_3,
            self.op_multiply_5,
            self.op_scale_1,
            self.op_divide_1,
            self.op_add_0,
            self.op_full_2,
            self.op_scale_2,
            self.op_exp_0,
            self.op_full_3,
            self.op_scale_3,
            self.op_full_4,
            self.op_scale_4,
            self.op_scale_5,
            self.op_divide_2,
        ]

    def op_full_0(self, data_1, data_2, data_0):
    
        # EarlyReturn(0, 0)

        # pd_op.full: (1xi32) <- ()
        full_0 = paddle._C_ops.full([1], float('2'), paddle.int32, paddle.core.CPUPlace())

        return [data_1, data_2, data_0, full_0]

    def op_assign_0(self, data_1, data_2, data_0, full_0):
    
        # EarlyReturn(0, 1)

        # pd_op.assign: (1xi32) <- (1xi32)
        assign_0 = full_0

        return [data_1, data_2, data_0, full_0, assign_0]

    def op_split_with_num_0(self, data_1, data_2, data_0, full_0, assign_0):
    
        # EarlyReturn(0, 2)

        # pd_op.split_with_num: ([-1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32]) <- (-1x-1x-1x-1xf32, 1xi32)
        split_with_num_0 = paddle._C_ops.split_with_num(data_0, 4, full_0)

        return [data_1, data_2, full_0, assign_0, split_with_num_0]

    def op_split_0(self, data_1, data_2, full_0, assign_0, split_with_num_0):
    
        # EarlyReturn(0, 3)

        # builtin.split: (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32) <- ([-1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32, -1x-1x-1x-1xf32])
        split_0, split_1, split_2, split_3, = split_with_num_0

        return [data_1, data_2, full_0, assign_0, split_0, split_1, split_2, split_3]

    def op_full_int_array_0(self, data_1, data_2, full_0, assign_0, split_0, split_1, split_2, split_3):
    
        # EarlyReturn(0, 4)

        # pd_op.full_int_array: (1xi64) <- ()
        full_int_array_0 = [0]

        return [data_1, data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0]

    def op_unsqueeze_0(self, data_1, data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0):
    
        # EarlyReturn(0, 5)

        # pd_op.unsqueeze: (1x-1x-1x-1xf32, 0x-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xi64)
        unsqueeze_0, unsqueeze_1 = (lambda x, f: f(x))(paddle._C_ops.unsqueeze(data_1, full_int_array_0), lambda out: out if isinstance(out, (list, tuple)) else (out, None))

        return [data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1]

    def op_subtract_0(self, data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1):
    
        # EarlyReturn(0, 6)

        # pd_op.subtract: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        subtract_0 = split_1 - split_0

        return [data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0]

    def op_subtract_1(self, data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0):
    
        # EarlyReturn(0, 7)

        # pd_op.subtract: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        subtract_1 = split_3 - split_0

        return [data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1]

    def op_full_int_array_1(self, data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1):
    
        # EarlyReturn(0, 8)

        # pd_op.full_int_array: (3xi64) <- ()
        full_int_array_1 = [2, 2, 1]

        return [data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, full_int_array_1]

    def op_split_1(self, data_2, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, full_int_array_1):
    
        # EarlyReturn(0, 9)

        # pd_op.split: ([-1x-1x-1xf32, -1x-1x-1xf32, -1x-1x-1xf32]) <- (-1x-1x-1xf32, 3xi64, 1xi32)
        split_4 = paddle._C_ops.split(data_2, full_int_array_1, assign_0)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_4]

    def op_split_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_4):
    
        # EarlyReturn(0, 10)

        # builtin.split: (-1x-1x-1xf32, -1x-1x-1xf32, -1x-1x-1xf32) <- ([-1x-1x-1xf32, -1x-1x-1xf32, -1x-1x-1xf32])
        split_5, split_6, split_7, = split_4

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_5, split_6, split_7]

    def op_full_int_array_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_5, split_6, split_7):
    
        # EarlyReturn(0, 11)

        # pd_op.full_int_array: (1xi64) <- ()
        full_int_array_2 = [2]

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_5, split_6, split_7, full_int_array_2]

    def op_unsqueeze_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_5, split_6, split_7, full_int_array_2):
    
        # EarlyReturn(0, 12)

        # pd_op.unsqueeze: (-1x-1x1x-1xf32, 0x-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xi64)
        unsqueeze_2, unsqueeze_3 = (lambda x, f: f(x))(paddle._C_ops.unsqueeze(split_5, full_int_array_2), lambda out: out if isinstance(out, (list, tuple)) else (out, None))

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3]

    def op_subtract_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3):
    
        # EarlyReturn(0, 13)

        # pd_op.subtract: (-1x-1x-1x-1xf32) <- (1x-1x-1x-1xf32, -1x-1x1x-1xf32)
        subtract_2 = unsqueeze_0 - unsqueeze_2

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2]

    def op_multiply_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2):
    
        # EarlyReturn(0, 14)

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_0 = subtract_2 * subtract_0

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0]

    def op_full_int_array_3(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0):
    
        # EarlyReturn(0, 15)

        # pd_op.full_int_array: (1xi64) <- ()
        full_int_array_3 = [-1]

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3]

    def op_assign_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3):
    
        # EarlyReturn(0, 16)

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_1 = full_int_array_3

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1]

    def op_assign_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1):
    
        # EarlyReturn(0, 17)

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_2 = full_int_array_3

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2]

    def op_assign_3(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2):
    
        # EarlyReturn(0, 18)

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_3 = full_int_array_3

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3]

    def op_assign_4(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3):
    
        # EarlyReturn(0, 19)

        # pd_op.assign: (1xi64) <- (1xi64)
        assign_4 = full_int_array_3

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4]

    def op_sum_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4):
    
        # EarlyReturn(0, 20)

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_0 = paddle._C_ops.sum(multiply_0, full_int_array_3, None, False)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0]

    def op_multiply_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0):
    
        # EarlyReturn(0, 21)

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_1 = subtract_2 * subtract_1

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1]

    def op_sum_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1):
    
        # EarlyReturn(0, 22)

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_1 = paddle._C_ops.sum(multiply_1, assign_4, None, False)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1]

    def op_multiply_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1):
    
        # EarlyReturn(0, 23)

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_2 = subtract_0 * subtract_0

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2]

    def op_sum_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2):
    
        # EarlyReturn(0, 24)

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_2 = paddle._C_ops.sum(multiply_2, assign_3, None, False)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sum_2]

    def op_sqrt_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sum_2):
    
        # EarlyReturn(0, 25)

        # pd_op.sqrt: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        sqrt_0 = paddle.sqrt(sum_2)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0]

    def op_multiply_3(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0):
    
        # EarlyReturn(0, 26)

        # pd_op.multiply: (-1x-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, -1x-1x-1x-1xf32)
        multiply_3 = subtract_1 * subtract_1

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3]

    def op_sum_3(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3):
    
        # EarlyReturn(0, 27)

        # pd_op.sum: (-1x-1x-1xf32) <- (-1x-1x-1x-1xf32, 1xi64)
        sum_3 = paddle._C_ops.sum(multiply_3, assign_2, None, False)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sum_3]

    def op_sqrt_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sum_3):
    
        # EarlyReturn(0, 28)

        # pd_op.sqrt: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        sqrt_1 = paddle.sqrt(sum_3)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1]

    def op_min_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1):
    
        # EarlyReturn(0, 29)

        # pd_op.min: (-1x-1x1xf32) <- (-1x-1x-1xf32, 1xi64)
        min_0 = paddle._C_ops.min(split_6, assign_1, True)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0]

    def op_pow_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0):
    
        # EarlyReturn(0, 30)

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_0 = paddle._C_ops.pow(sum_0, float('2'))

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0]

    def op_pow_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0):
    
        # EarlyReturn(0, 31)

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_1 = paddle._C_ops.pow(sqrt_0, float('3'))

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1]

    def op_multiply_4(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1):
    
        # EarlyReturn(0, 32)

        # pd_op.multiply: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x1xf32)
        multiply_4 = pow_1 * min_0

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4]

    def op_full_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4):
    
        # EarlyReturn(0, 33)

        # pd_op.full: (1xf32) <- ()
        full_1 = paddle._C_ops.full([1], float('1'), paddle.float32, paddle.core.CPUPlace())

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4, full_1]

    def op_assign_5(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4, full_1):
    
        # EarlyReturn(0, 34)

        # pd_op.assign: (1xf32) <- (1xf32)
        assign_5 = full_1

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4, full_1, assign_5]

    def op_assign_6(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4, full_1, assign_5):
    
        # EarlyReturn(0, 35)

        # pd_op.assign: (1xf32) <- (1xf32)
        assign_6 = full_1

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4, full_1, assign_5, assign_6]

    def op_scale_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, multiply_4, full_1, assign_5, assign_6):
    
        # EarlyReturn(0, 36)

        # pd_op.scale: (-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xf32)
        scale_0 = paddle._C_ops.scale(multiply_4, full_1, float('1e-09'), True)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0]

    def op_divide_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0):
    
        # EarlyReturn(0, 37)

        # pd_op.divide: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x-1xf32)
        divide_0 = pow_0 / scale_0

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0]

    def op_pow_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0):
    
        # EarlyReturn(0, 38)

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_2 = paddle._C_ops.pow(sum_1, float('2'))

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2]

    def op_pow_3(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2):
    
        # EarlyReturn(0, 39)

        # pd_op.pow: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        pow_3 = paddle._C_ops.pow(sqrt_1, float('3'))

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3]

    def op_multiply_5(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3):
    
        # EarlyReturn(0, 40)

        # pd_op.multiply: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x1xf32)
        multiply_5 = pow_3 * min_0

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, multiply_5]

    def op_scale_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, multiply_5):
    
        # EarlyReturn(0, 41)

        # pd_op.scale: (-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xf32)
        scale_1 = paddle._C_ops.scale(multiply_5, assign_6, float('1e-09'), True)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1]

    def op_divide_1(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1):
    
        # EarlyReturn(0, 42)

        # pd_op.divide: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x-1xf32)
        divide_1 = pow_2 / scale_1

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1]

    def op_add_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1):
    
        # EarlyReturn(0, 43)

        # pd_op.add: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x-1xf32)
        add_0 = divide_0 + divide_1

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, add_0]

    def op_full_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, add_0):
    
        # EarlyReturn(0, 44)

        # pd_op.full: (1xf32) <- ()
        full_2 = paddle._C_ops.full([1], float('-6'), paddle.float32, paddle.core.CPUPlace())

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, add_0, full_2]

    def op_scale_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, add_0, full_2):
    
        # EarlyReturn(0, 45)

        # pd_op.scale: (-1x-1x-1xf32) <- (-1x-1x-1xf32, 1xf32)
        scale_2 = paddle._C_ops.scale(add_0, full_2, float('0'), True)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, scale_2]

    def op_exp_0(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, scale_2):
    
        # EarlyReturn(0, 46)

        # pd_op.exp: (-1x-1x-1xf32) <- (-1x-1x-1xf32)
        exp_0 = paddle._C_ops.exp(scale_2)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0]

    def op_full_3(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0):
    
        # EarlyReturn(0, 47)

        # pd_op.full: (1xf32) <- ()
        full_3 = paddle._C_ops.full([1], float('0.0833333'), paddle.float32, paddle.core.CPUPlace())

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3]

    def op_scale_3(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3):
    
        # EarlyReturn(0, 48)

        # pd_op.scale: (-1x-1x1xf32) <- (-1x-1x1xf32, 1xf32)
        scale_3 = paddle._C_ops.scale(min_0, full_3, float('0'), True)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, scale_3]

    def op_full_4(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, scale_3):
    
        # EarlyReturn(0, 49)

        # pd_op.full: (1xf32) <- ()
        full_4 = paddle._C_ops.full([1], float('6.28319'), paddle.float32, paddle.core.CPUPlace())

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, scale_3, full_4]

    def op_scale_4(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, scale_3, full_4):
    
        # EarlyReturn(0, 50)

        # pd_op.scale: (-1x-1x1xf32) <- (-1x-1x1xf32, 1xf32)
        scale_4 = paddle._C_ops.scale(scale_3, full_4, float('0'), True)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, full_4, scale_4]

    def op_scale_5(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, full_4, scale_4):
    
        # EarlyReturn(0, 51)

        # pd_op.scale: (-1x-1x1xf32) <- (-1x-1x1xf32, 1xf32)
        scale_5 = paddle._C_ops.scale(scale_4, assign_5, float('1e-09'), True)

        return [full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, full_4, scale_5]

    def op_divide_2(self, full_0, assign_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, assign_1, assign_2, assign_3, assign_4, sum_0, multiply_1, sum_1, multiply_2, sqrt_0, multiply_3, sqrt_1, min_0, pow_0, pow_1, full_1, assign_5, assign_6, scale_0, divide_0, pow_2, pow_3, scale_1, divide_1, full_2, exp_0, full_3, full_4, scale_5):
    
        # EarlyReturn(0, 52)

        # pd_op.divide: (-1x-1x-1xf32) <- (-1x-1x-1xf32, -1x-1x1xf32)
        divide_2 = exp_0 / scale_5

        return [full_0, split_0, split_1, split_2, split_3, full_int_array_0, unsqueeze_0, unsqueeze_1, subtract_0, subtract_1, assign_0, split_6, split_7, full_int_array_2, unsqueeze_2, unsqueeze_3, subtract_2, multiply_0, full_int_array_3, sum_0, multiply_1, assign_4, sum_1, multiply_2, assign_3, sqrt_0, multiply_3, assign_2, sqrt_1, assign_1, min_0, pow_0, pow_1, full_1, scale_0, divide_0, pow_2, pow_3, assign_6, scale_1, divide_1, full_2, full_3, full_4, assign_5, scale_5, exp_0, divide_2]

@unittest.skipIf(need_skip, skip_message)
class Test_builtin_module_201_0_0(CinnTestBase, unittest.TestCase):
    def prepare_data(self):
        self.inputs = [
            # data_1
            paddle.uniform([1, 21824, 2], dtype='float32', min=0, max=0.5),
            # data_2
            paddle.uniform([1, 6, 5], dtype='float32', min=0, max=0.5),
            # data_0
            paddle.uniform([1, 6, 4, 2], dtype='float32', min=0, max=0.5),
        ]
        for input in self.inputs:
            input.stop_gradient = True

    def apply_to_static(self, net, use_cinn):
        build_strategy = paddle.static.BuildStrategy()
        input_spec = [
            # data_1
            paddle.static.InputSpec(shape=[None, None, None], dtype='float32'),
            # data_2
            paddle.static.InputSpec(shape=[None, None, None], dtype='float32'),
            # data_0
            paddle.static.InputSpec(shape=[None, None, None, None], dtype='float32'),
        ]
        build_strategy.build_cinn_pass = use_cinn
        return paddle.jit.to_static(
            net,
            input_spec=input_spec,
            build_strategy=build_strategy,
            full_graph=True,
        )

    def entry(self, use_cinn):
        net = Block_builtin_module_201_0_0()
        if GetEnvVarEnableJit():
            net = self.apply_to_static(net, use_cinn)
        paddle.seed(2024)
        out = net(*self.inputs)
        return out

    def test_entry(self):
        if AthenaTryRunEnabled():
            if try_run_exit_code == 0:
                # All unittest cases passed.
                return
            if try_run_exit_code < 0:
                # program panicked.
                raise RuntimeError(f"panicked. panic stderr have been reported by the unittest `TestTryRun.test_panic`.")
        self._test_entry()

if __name__ == '__main__':
    unittest.main()
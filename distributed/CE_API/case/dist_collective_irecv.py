#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
/***************************************************************************
  *
  * Copyright (c) 2019 Baidu.com, Inc. All Rights Reserved
  * @file dist_collective_send.py
  * @author liujie44@baidu.com
  * @date 2021-11-09 11:00
  * @brief
  *
  **************************************************************************/
"""
import numpy as np
import paddle
from paddle.distributed import init_parallel_env

from utils import run_priority

types = [np.float16, np.float32, np.float64, np.int32, np.int64, np.int8, np.uint8]
init_parallel_env()


@run_priority(level="P0")
def test_collective_irecv():
    """test_collective_irecv"""
    for t in types:
        if paddle.distributed.ParallelEnv().rank == 0:
            np_data = np.array([7, 8, 9]).astype(t)
            data = paddle.to_tensor(np_data)
            paddle.distributed.irecv(data, src=1)
        else:
            np_data = np.array([1, 2, 3]).astype(t)
            data = paddle.to_tensor(np_data)
            paddle.distributed.isend(data, dst=0)
        out = data.numpy()
        assert out[0] == 1
        assert out[1] == 2
        assert out[2] == 3
        print("test_collective_irecv %s... ok" % t)


if __name__ == "__main__":
    test_collective_irecv()

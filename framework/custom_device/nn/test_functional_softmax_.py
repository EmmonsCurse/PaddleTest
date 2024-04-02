#!/bin/env python
# -*- coding: utf-8 -*-
# encoding=utf-8 vi:ts=4:sw=4:expandtab:ft=python
"""
test_functional_softmax_
"""
from apibase import APIBase
import paddle
import pytest
import numpy as np


class TestFunctionalSoftmax(APIBase):
    """
    test
    """

    def hook(self):
        """
        implement
        """
        self.types = [np.float32, np.float64]
        # self.debug = True
        # self.static = True
        # enable check grad
        self.enable_backward = False


obj = TestFunctionalSoftmax(paddle.nn.functional.softmax_)


@pytest.mark.api_nn_softmax_vartype
def test_functional_softmax_base():
    """
    base
    """
    x = np.array(
        [
            [[2.0, 3.0, 4.0, 5.0], [3.0, 4.0, 5.0, 6.0], [7.0, 8.0, 8.0, 9.0]],
            [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [6.0, 7.0, 8.0, 9.0]],
        ]
    )
    res = np.array(
        [
            [
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.07232949, 0.19661193, 0.19661193, 0.53444665],
            ],
            [
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
            ],
        ]
    )
    obj.base(res=res, x=x)


@pytest.mark.api_nn_softmax_parameters
def test_functional_softmax():
    """
    default
    """
    x = np.array(
        [
            [[2.0, 3.0, 4.0, 5.0], [3.0, 4.0, 5.0, 6.0], [7.0, 8.0, 8.0, 9.0]],
            [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [6.0, 7.0, 8.0, 9.0]],
        ]
    )
    res = np.array(
        [
            [
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.07232949, 0.19661193, 0.19661193, 0.53444665],
            ],
            [
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
            ],
        ]
    )
    obj.run(res=res, x=x)


@pytest.mark.api_nn_softmax_parameters
def test_functional_softmax1():
    """
    axis = 1
    """
    x = np.array(
        [
            [[2.0, 3.0, 4.0, 5.0], [3.0, 4.0, 5.0, 6.0], [7.0, 8.0, 8.0, 9.0]],
            [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [6.0, 7.0, 8.0, 9.0]],
        ]
    )
    res = np.array(
        [
            [
                [0.00657326, 0.00657326, 0.01714783, 0.01714783],
                [0.01786798, 0.01786798, 0.04661262, 0.04661262],
                [0.97555875, 0.97555875, 0.93623955, 0.93623955],
            ],
            [
                [0.00490169, 0.00490169, 0.00490169, 0.00490169],
                [0.26762315, 0.26762315, 0.26762315, 0.26762315],
                [0.72747516, 0.72747516, 0.72747516, 0.72747516],
            ],
        ]
    )
    obj.run(res=res, x=x, axis=1)


@pytest.mark.api_nn_softmax_exception
def test_functional_softmax2():
    """
    exception axis = 4
    """
    x = np.array(
        [
            [[2.0, 3.0, 4.0, 5.0], [3.0, 4.0, 5.0, 6.0], [7.0, 8.0, 8.0, 9.0]],
            [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [6.0, 7.0, 8.0, 9.0]],
        ]
    )

    obj.exception(etype="InvalidArgument", x=x, axis=4)


@pytest.mark.api_nn_softmax_parameters
def test_functional_softmax3():
    """
    axis=2
    """
    x = np.array(
        [
            [[2.0, 3.0, 4.0, 5.0], [3.0, 4.0, 5.0, 6.0], [7.0, 8.0, 8.0, 9.0]],
            [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [6.0, 7.0, 8.0, 9.0]],
        ]
    )
    res = np.array(
        [
            [
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.07232949, 0.19661193, 0.19661193, 0.53444665],
            ],
            [
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
                [0.0320586, 0.08714432, 0.23688282, 0.64391426],
            ],
        ]
    )
    obj.run(res=res, x=x, axis=2)


@pytest.mark.api_nn_softmax_parameters
def test_functional_softmax4():
    """
    axis=0
    """
    x = np.array(
        [
            [[2.0, 3.0, 4.0, 5.0], [3.0, 4.0, 5.0, 6.0], [7.0, 8.0, 8.0, 9.0]],
            [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [6.0, 7.0, 8.0, 9.0]],
        ]
    )
    # 算法实现
    res = x.reshape(2, 12)
    res = (np.exp(res) / sum(np.exp(res))).reshape(2, 3, 4)
    obj.run(res=res, x=x, axis=0)

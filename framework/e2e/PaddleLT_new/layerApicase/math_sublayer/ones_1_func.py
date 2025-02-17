import numpy as np
import paddle


class LayerCase(paddle.nn.Layer):
    """
    case名称: ones_1
    api简介: 创建形状为 shape 、数据类型为 dtype 且值全为1的Tensor
    """

    def __init__(self):
        super(LayerCase, self).__init__()

    def forward(self, ):
        """
        forward
        """
        out = paddle.ones( shape=[2, 3, 4, 4], dtype='bool', )
        return out



def create_inputspec(): 
    inputspec = ( 
    )
    return inputspec

def create_tensor_inputs():
    """
    paddle tensor
    """
    inputs = ()
    return inputs


def create_numpy_inputs():
    """
    numpy array
    """
    inputs = ()
    return inputs


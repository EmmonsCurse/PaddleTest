import numpy as np
import paddle


class LayerCase(paddle.nn.Layer):
    """
    case名称: Conv3DTranspose_6
    api简介: 3维反卷积
    """

    def __init__(self):
        super(LayerCase, self).__init__()
        self.func = paddle.nn.Conv3DTranspose(in_channels=3, out_channels=3, kernel_size=[3, 3, 3], stride=2, padding=[1, 0, 1], dilation=1, groups=3, data_format='NDHWC', output_padding=1, )

    def forward(self, data, ):
        """
        forward
        """
        out = self.func(data, )
        return out



def create_inputspec(): 
    inputspec = ( 
        paddle.static.InputSpec(shape=(-1, -1, -1, -1, 3), dtype=paddle.float32, stop_gradient=False), 
    )
    return inputspec

def create_tensor_inputs():
    """
    paddle tensor
    """
    inputs = (paddle.to_tensor(0 + (1 - 0) * np.random.random([2, 2, 2, 2, 3]).astype('float32'), dtype='float32', stop_gradient=False), )
    return inputs


def create_numpy_inputs():
    """
    numpy array
    """
    inputs = (0 + (1 - 0) * np.random.random([2, 2, 2, 2, 3]).astype('float32'), )
    return inputs


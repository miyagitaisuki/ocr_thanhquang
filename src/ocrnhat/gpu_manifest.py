"""SINH TỰ ĐỘNG bởi scripts/build_gpu_manifest.py. Không sửa tay."""
PYTHON_TAG = "cp312"
# Gói GPU tải theo yêu cầu. Chọn gói theo driver/compute capability: gpu_pack.select_pack().
PACKS = {
    "cu13": {
        "label": 'CUDA 13',
        "min_driver": (580, 0),
        "min_cc": (7, 5),
        "total_bytes": 1295270054,
        "wheels": [   # (tên file, URL, SHA-256, byte)
            ('onnxruntime_gpu-1.31.1-cp312-cp312-win_amd64.whl', 'https://files.pythonhosted.org/packages/05/ec/fe99397c6d6582fe26502b608f132a1c7748381fa72523c8b7a0686b9b14/onnxruntime_gpu-1.31.1-cp312-cp312-win_amd64.whl', '2bb1e9373baba88f6415257f5b6a589d23e23c16004f7d89adf4344eada5749e', 168098228),
            ('nvidia_cuda_nvrtc-13.4.92-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/64/5b/aa91896f64444eff1dd7f189f4db05046c7f0ba08c0f531283c1c1aac581/nvidia_cuda_nvrtc-13.4.92-py3-none-win_amd64.whl', '6af7ac5372920f6a7a560d0699348560fe44cb52c1d722d6afd3119f8af948c4', 46972283),
            ('nvidia_cuda_runtime-13.4.92-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/86/00/d5436004268f049214193659ebc36550b5ef3925c3d13b4cc980e13be6f5/nvidia_cuda_runtime-13.4.92-py3-none-win_amd64.whl', '08dca5e4aba480c2fd5b55075c0fa71b84ef9dcf0521f2d58baa14a803a7311c', 2778543),
            ('nvidia_cufft-12.4.0.43-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/7b/cc/be7fe31058127336a66c88414a2ecc6beecf680baf85994a43eaf292b202/nvidia_cufft-12.4.0.43-py3-none-win_amd64.whl', '4ff7075f2d0b5f69291f70938d37a86ec632cbe5747184c74ba1f50f17accacc', 160953139),
            ('nvidia_curand-10.4.4.72-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/e2/d4/f59ab342b82ff05ff27d674acd470ba625d788bf71338f7da6c89669d6b9/nvidia_curand-10.4.4.72-py3-none-win_amd64.whl', 'e0bce83e083ef25976ee74f59e8f067c15149a74538f1be6c2462e286e7c9c68', 56731059),
            ('nvidia_cublas-13.8.0.4-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/a3/df/f1246959833e2c437db8be3e5b477f66b87f8817821ed40de6c7561c9a36/nvidia_cublas-13.8.0.4-py3-none-win_amd64.whl', '8c5494423bb8a46822cb6b0cb95d7fa4be2d7b96a31155dff083839ec8297910', 423266897),
            ('nvidia_cudnn_cu13-9.27.0.42-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/87/6a/e55ff0ac26a5c6e2b21f41c9d04ad096b4ed6da593fba7e25845c61b0532/nvidia_cudnn_cu13-9.27.0.42-py3-none-win_amd64.whl', '7d96f634adafd55c72231eb0500ca77ab109ec8ebff7b33000b76e081bc4558e', 436469905),
        ],
    },
    "cu12": {
        "label": 'CUDA 12',
        "min_driver": (576, 2),
        "min_cc": (7, 5),
        "total_bytes": 1859997659,
        "wheels": [   # (tên file, URL, SHA-256, byte)
            ('onnxruntime_gpu-1.22.0-cp312-cp312-win_amd64.whl', 'https://files.pythonhosted.org/packages/48/9e/f95af15627c8b9f866f2e372e467a9f1e14e7ebec224ed4b8e71ce970c81/onnxruntime_gpu-1.22.0-cp312-cp312-win_amd64.whl', '89cfd71e1ba17a4668e8770e344f22cde64bfd70b2ad3d03b8a390d4414b5995', 214923964),
            ('nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/52/de/823919be3b9d0ccbf1f784035423c5f18f4267fb0123558d58b813c6ec86/nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl', '72972ebdcf504d69462d3bcd67e7b81edd25d0fb85a2c46d3ea3517666636349', 76408187),
            ('nvidia_cuda_runtime_cu12-12.9.79-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/59/df/e7c3a360be4f7b93cee39271b792669baeb3846c58a4df6dfcf187a7ffab/nvidia_cuda_runtime_cu12-12.9.79-py3-none-win_amd64.whl', '8e018af8fa02363876860388bd10ccb89eb9ab8fb0aa749aaf58430a9f7c4891', 3591604),
            ('nvidia_cufft_cu12-11.4.1.4-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/20/ee/29955203338515b940bd4f60ffdbc073428f25ef9bfbce44c9a066aedc5c/nvidia_cufft_cu12-11.4.1.4-py3-none-win_amd64.whl', '8e5bfaac795e93f80611f807d42844e8e27e340e0cde270dcb6c65386d795b80', 200067309),
            ('nvidia_curand_cu12-10.3.10.19-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/e5/98/1bd66fd09cbe1a5920cb36ba87029d511db7cca93979e635fd431ad3b6c0/nvidia_curand_cu12-10.3.10.19-py3-none-win_amd64.whl', 'e8129e6ac40dc123bd948e33d3e11b4aa617d87a583fa2f21b3210e90c743cde', 68774847),
            ('nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl', '623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661', 553162896),
            ('nvidia_cudnn_cu12-9.27.0.42-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/aa/38/f856579877f7c1c5066e61182e7de7bc27bf35a78c8d1b0fa592e6985bc4/nvidia_cudnn_cu12-9.27.0.42-py3-none-win_amd64.whl', '06e9b0026f3bad97d2b58666330fabec04fe1672f776661ecb0ce0029c27f142', 743068852),
        ],
    },
}

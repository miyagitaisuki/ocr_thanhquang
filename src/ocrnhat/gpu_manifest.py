"""SINH TỰ ĐỘNG bởi scripts/build_gpu_manifest.py. Không sửa tay."""
PACK_VERSION = "2026.10-cu13"
PYTHON_TAG = "cp312"
TOTAL_BYTES = 1295270054
# (tên file wheel, URL, SHA-256, dung lượng byte)
WHEELS = [
    ('onnxruntime_gpu-1.31.1-cp312-cp312-win_amd64.whl', 'https://files.pythonhosted.org/packages/05/ec/fe99397c6d6582fe26502b608f132a1c7748381fa72523c8b7a0686b9b14/onnxruntime_gpu-1.31.1-cp312-cp312-win_amd64.whl', '2bb1e9373baba88f6415257f5b6a589d23e23c16004f7d89adf4344eada5749e', 168098228),
    ('nvidia_cuda_nvrtc-13.4.92-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/64/5b/aa91896f64444eff1dd7f189f4db05046c7f0ba08c0f531283c1c1aac581/nvidia_cuda_nvrtc-13.4.92-py3-none-win_amd64.whl', '6af7ac5372920f6a7a560d0699348560fe44cb52c1d722d6afd3119f8af948c4', 46972283),
    ('nvidia_cuda_runtime-13.4.92-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/86/00/d5436004268f049214193659ebc36550b5ef3925c3d13b4cc980e13be6f5/nvidia_cuda_runtime-13.4.92-py3-none-win_amd64.whl', '08dca5e4aba480c2fd5b55075c0fa71b84ef9dcf0521f2d58baa14a803a7311c', 2778543),
    ('nvidia_cufft-12.4.0.43-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/7b/cc/be7fe31058127336a66c88414a2ecc6beecf680baf85994a43eaf292b202/nvidia_cufft-12.4.0.43-py3-none-win_amd64.whl', '4ff7075f2d0b5f69291f70938d37a86ec632cbe5747184c74ba1f50f17accacc', 160953139),
    ('nvidia_curand-10.4.4.72-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/e2/d4/f59ab342b82ff05ff27d674acd470ba625d788bf71338f7da6c89669d6b9/nvidia_curand-10.4.4.72-py3-none-win_amd64.whl', 'e0bce83e083ef25976ee74f59e8f067c15149a74538f1be6c2462e286e7c9c68', 56731059),
    ('nvidia_cublas-13.8.0.4-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/a3/df/f1246959833e2c437db8be3e5b477f66b87f8817821ed40de6c7561c9a36/nvidia_cublas-13.8.0.4-py3-none-win_amd64.whl', '8c5494423bb8a46822cb6b0cb95d7fa4be2d7b96a31155dff083839ec8297910', 423266897),
    ('nvidia_cudnn_cu13-9.27.0.42-py3-none-win_amd64.whl', 'https://files.pythonhosted.org/packages/87/6a/e55ff0ac26a5c6e2b21f41c9d04ad096b4ed6da593fba7e25845c61b0532/nvidia_cudnn_cu13-9.27.0.42-py3-none-win_amd64.whl', '7d96f634adafd55c72231eb0500ca77ab109ec8ebff7b33000b76e081bc4558e', 436469905),
]

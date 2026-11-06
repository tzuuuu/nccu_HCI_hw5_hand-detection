"""Download the versioned official model once; verify bundle before replacement."""

import hashlib
import ssl
import certifi
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
MODEL_PATH = Path(__file__).parent / 'models' / 'hand_landmarker.task'
MODEL_SHA256 = 'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'


def download():
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODEL_PATH.with_suffix('.part')
    try:
        with urlopen(MODEL_URL, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as response, temporary.open('wb') as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('模型 SHA256 不符，保留原有模型')
        with ZipFile(temporary) as bundle:
            names = bundle.namelist()
            if bundle.testzip() or not any('hand_landmarks' in n for n in names) or not any('hand_detector' in n for n in names):
                raise ValueError('下載的模型封裝不完整')
        temporary.replace(MODEL_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    print(MODEL_PATH)
    print('SHA256:', hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest())


if __name__ == '__main__':
    download()

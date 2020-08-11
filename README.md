# niutranspy

NiuTrans SDK for Python

## Installation

```shell script
pip install niutranspy
```

## Usage

```python
from niutranspy import Niutrans, Translator

NIUTRANS_API_KEY = '*************'
CACHE_DIR = '/home/a/niutranspy/'

niutrans = Niutrans(api_key=NIUTRANS_API_KEY)
translator = Translator(cache_dir=CACHE_DIR, niutrans=niutrans)
print(translator.translate('测试', to_lang='en'))
```

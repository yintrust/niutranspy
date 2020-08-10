from niutrans import Niutrans
from client import Translator

NIUTRANS_API_KEY = '1ad1a209b7ea5404974b6799b7244c43'
niutrans = Niutrans(api_key=NIUTRANS_API_KEY)
translator = Translator('/home/a/Desktop/niutrans', niutrans=niutrans)
print(translator.translate('测试', to_lang='en'))

import json
import logging
from typing import Union, Tuple

import requests
import threading
from bs4 import BeautifulSoup
from bs4.element import NavigableString

from backend import _TranslationBackend
from utils import _try_despite_of_errors
from constants import NIUTRANS_API_URL, NIUTRANS_XML_API_URL

_lock = threading.RLock()
_caches = {}
_old_caches = {}
_log = logging.getLogger(__name__)
# _niutrans_stats = LocalStatsLogger(_log.info, 400, 'Niutrans translated {} items')


class Niutrans(_TranslationBackend):
    def __init__(self, api_key):
        if not api_key:
            _log.warning('apikey being empty, dummy translator is used.')
        self._data = {'apikey': api_key}  # "from" and "to" are also necessary

    def is_disabled(self) -> bool:
        return not self._data['apikey']

    @staticmethod
    def max_translation_block_size() -> int:
        return 5000

    def _can_translate(self, soup):
        if not soup.content or len(str(soup)) <= self.max_translation_block_size():
            return True
        if isinstance(soup, NavigableString):
            return False
        return all(self._can_translate(sub) for sub in soup)

    def _pre_check(self, src_text: str, from_lang: str, to_lang: str, is_plain_str: bool) -> Union[BaseException, None]:
        # if from_lang in {'ja'} and is_plain_str and to_lang != 'en':
        #     # TMT does not support translating Japanese to English. The task has to be done by Niutrans
        #     return ValueError(f"Niutrans: disabled from translating {from_lang} text to {to_lang}")
        if self._can_translate(BeautifulSoup(f'<div>{src_text}</div>', 'html.parser').div):
            return None
        else:
            return ValueError(f'Niutrans: Length exceeds 5000 chars: {src_text!r}')

    def _translate_base(self, api_url: str, src_text: str, from_lang: str, to_lang: str, cache) -> str:
        src_text = src_text.strip()
        if not src_text: return ''  # noqa: E701
        tgt_text = cache.get(src_text)
        if tgt_text: return tgt_text  # noqa: E701
        data_post = {'src_text': src_text, 'from': from_lang, 'to': to_lang}
        data_post.update(self._data)

        exceptions = (requests.exceptions.ConnectionError,)
        try:
            data = _try_despite_of_errors(lambda: json.loads(requests.post(api_url, data=data_post).text), exceptions)
        except exceptions as e:
            raise e

        if 'error_code' in data:
            raise ValueError(f"{data.get('error_code')}: {data.get('error_msg')} - {src_text}")

        tgt_text = data.get('tgt_text', '').strip()
        if not tgt_text:
            raise ValueError(f'{src_text!r} was translated to empty target text: {data!r}')
        # _niutrans_stats()
        return tgt_text

    def _translate_plain_text(self, src_text: str, from_lang: str, to_lang: str,
                              cache) -> Tuple[str, Union[BaseException, None]]:
        try:
            return self._translate_base(NIUTRANS_API_URL, src_text, from_lang, to_lang, cache), None
        except ValueError as e:
            return '', e

    def _translate_xml(self, src_text: str, from_lang: str, to_lang: str, cache) -> str:
        return self._translate_base(NIUTRANS_XML_API_URL, src_text, from_lang, to_lang, cache)

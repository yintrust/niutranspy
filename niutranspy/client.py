import logging
import threading
from os import path, makedirs
from typing import Union

from opencc import OpenCC
from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString

from niutranspy.utils import html_to_text, _load_dicts, get_lang

_log = logging.getLogger(__name__)
_lock = threading.RLock()


class Translator(object):
    CACHE_FILE_NAME = 'translation/cache.db'
    SUGGESTION_FILE_NAME = 'translation/suggestion.txt'
    LANGUAGES = {'ar', 'zh', 'en', 'ko', 'pt', 'es', 'de', 'da', 'fr', 'fi', 'sv', 'he', 'nl', 'ru', 'th', 'ja'}

    def __init__(self, cache_dir: str, niutrans):
        self._filename = path.join(cache_dir, self.CACHE_FILE_NAME)
        self._zh_hant_to_zh_hans = OpenCC('t2s').convert
        self._dummy = niutrans.is_disabled()
        self._niutrans = niutrans
        dic = {}
        valid_languages = {'X', '='} | Translator.LANGUAGES
        with open(path.join(cache_dir, self.SUGGESTION_FILE_NAME)) as f:
            for i, l in enumerate(f):
                lang, s = l.strip().split(' ', maxsplit=1)
                assert lang in valid_languages, f'{i + 1}: invalid language: {lang}'
                dic[s.strip()[1:-1]] = lang
        self._lang_suggestion = dic
        _log.info(f'{len(dic)} items in the language suggestion dictionary')

    def _get_cache(self, from_lang, to_lang):
        assert len({from_lang, to_lang} & self.LANGUAGES) == 2, f'Invalid {from_lang!r} -> {to_lang!r}'
        return _load_dicts(self._filename, from_lang, to_lang)

    def suggest(self, from_lang: str, to_lang: str, src_text: str, target_text: str):
        """Update the translator's cache so that "src_text" will be translated as "target_text" in the future."""
        _log.debug(f'Suggest {src_text!r} ({from_lang}) as {target_text!r} ({to_lang})')
        with _lock:
            cache, old_cache = self._get_cache(from_lang, to_lang)
            old_target_text = cache.get(src_text)
            if old_target_text and old_target_text != target_text:
                _log.debug(f'Translation of [{from_lang}_{to_lang}]{src_text!r} changed: {old_target_text!r} -> {target_text!r}')  # noqa: E501
            cache[src_text] = target_text

    def translate(self, src_text: str, to_lang: str, from_lang=None) -> str:
        """Translates src_text to `to_lang`.

        It `from_lang` is not valid, auto-detection is performed to find it.
        """
        if self._dummy: return src_text  # noqa: E701
        if from_lang in {'ja', 'zh'} and all(ord(c) < 127 for c in src_text if not c.isspace()):
            return src_text
        src_soup = BeautifulSoup(src_text, 'html.parser')
        if not src_soup.get_text().strip():
            return src_text  # self-closed tag that without content

        if from_lang:
            with _lock:
                cache, old_cache = self._get_cache(from_lang, to_lang)
                target_text = cache.get(src_text)
                if not target_text and (src_text in old_cache):
                    cache[src_text] = target_text = old_cache[src_text]
                if target_text: return target_text  # noqa: E701

        if len(src_soup.contents) == 1 and isinstance(src_soup.contents[0], Tag):
            src_children = src_soup.contents[0].children
            full_target_str = src_text[:src_text.find('>', 1) + 1]  # attributes are included
            target_tail_str = f'</{src_soup.contents[0].name}>'
        else:
            src_children = src_soup.children
            full_target_str = target_tail_str = ''

        for src_tag in src_children:
            attrs = {}
            if isinstance(src_tag, Tag):
                attrs = src_tag.attrs
                src_tag.attrs = {}
            target_str = self._do_translation(str(src_tag), from_lang, to_lang,
                                              isinstance(src_tag, NavigableString))
            if not target_str: continue  # noqa: E701
            if attrs:
                target_tag = BeautifulSoup(target_str, 'html.parser').contents[0]
                target_tag.attrs = attrs
                target_str = str(target_tag)
            full_target_str += target_str

        full_target_str += target_tail_str
        return full_target_str

    def _do_translation(self, src_text: str, from_lang: Union[None, str], to_lang: str, is_plain_str: bool):
        assert to_lang in self.LANGUAGES, f'{to_lang} is not enabled in Translator.LANGUAGES yet'
        src_text = src_text.strip()
        if len(src_text) <= 1:
            if not src_text: return ''  # noqa: E701
            if ord(src_text) < 127: return src_text  # noqa: E701
        if from_lang not in self.LANGUAGES:
            if src_text in self._lang_suggestion:
                from_lang = self._lang_suggestion[src_text]
                if from_lang == 'X': return ''  # noqa: E701
                if from_lang == '=': return src_text  # noqa: E701
                _log.debug(f'Recognise {src_text!r} as {from_lang}')
                assert from_lang in self.LANGUAGES, from_lang
            else:
                tmp_src_text = html_to_text(src_text).strip().lower()
                if not tmp_src_text:
                    return ''  # it's a self closed html tag without text content
                good, from_lang = get_lang(tmp_src_text)
                if not good:
                    raise ValueError(f'= {src_text!r}')
            if from_lang not in self.LANGUAGES:
                raise ValueError(f'{from_lang} {repr(src_text)}')
        assert to_lang in {'en', 'zh'}
        if from_lang in {'ja', 'zh'} and all(ord(c) < 127 for c in src_text if not c.isspace()):
            return src_text
        if from_lang == 'zh':
            # it might be traditional Chinese. we need simplified Chinese
            src_text = self._zh_hant_to_zh_hans(src_text)
        if from_lang == to_lang:
            return src_text

        with _lock:
            cache, old_cache = self._get_cache(from_lang, to_lang)
            target_text = cache.get(src_text)
            if not target_text and (src_text in old_cache):
                cache[src_text] = target_text = old_cache[src_text]

        # If the source hits the cache, return the target immediately
        if target_text:
            return target_text

        # Otherwise, hit the translation
        target_text, err = '', None
        # if is_plain_str:
        #     target_text, err = _tmt(src_text, from_lang, to_lang, cache, is_plain_str)
        #     if err: _log.info(err)  # noqa: E701
        if not target_text:
            target_text, err = self._niutrans(src_text, from_lang, to_lang, cache, is_plain_str)
            if err: _log.debug(err)  # noqa: E701
        if not target_text:
            raise err or ValueError('All translator backends are disabled')

        # Increment count
        # _stats()

        # Write result to cache in RAM and return the target
        with _lock:
            cache[src_text] = target_text

        return target_text

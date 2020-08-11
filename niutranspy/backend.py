from typing import Dict, Union, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag

from niutranspy.utils import strip_soup_text


class _TranslationBackend(object):
    def __call__(self, src_text: str, from_lang: str, to_lang: str, cache: Dict[str, str],
                 is_plain_str: bool) -> Tuple[str, Union[BaseException, None]]:
        if self.is_disabled():
            return '', ValueError('Disabled')
        err = self._pre_check(src_text, from_lang, to_lang, is_plain_str)
        if err:
            return '', err

        block_size = self.max_translation_block_size()
        if any(len(piece) > block_size - 2 for piece in src_text.split('\n')):
            return '', ValueError(f'Length exceeds {block_size} chars: {src_text}')

        if is_plain_str:
            translated = []
            pieces, cnt = [], 0
            for piece in src_text.split('\n'):
                piece = piece.strip()  # in case of '\r\n'
                extra_cnt = len(piece) + 1
                if cnt + extra_cnt > block_size:
                    target_str, e = self._translate_plain_text('\n'.join(pieces), from_lang, to_lang, cache)
                    if e: return '', e  # noqa: E701
                    translated.append(target_str)
                    pieces.clear()
                    cnt = 0
                cnt += extra_cnt
                pieces.append(piece)

            # last pieces
            target_str, e = self._translate_plain_text('\n'.join(pieces), from_lang, to_lang, cache)
            if e: return '', e  # noqa: E701
            translated.append(target_str)
            # _stats()
            return '\n'.join(translated), None

        # else: it's XML text
        src_soup = BeautifulSoup(f'<div>{src_text}</div>', 'html.parser').div
        try:
            src_text = ''.join(self._tran(piece, from_lang, to_lang, cache) for piece in src_soup.children)
            # _stats()
            return src_text, None
        except ValueError as e:
            return '', e

    def _tran(self, src_soup: BeautifulSoup, from_lang: str, to_lang: str, cache: Dict[str, str]) -> str:
        src_text = str(src_soup)
        if src_text not in cache:
            if isinstance(src_soup, Tag):
                if not src_soup.contents:
                    cache[src_text] = src_text
                elif len(src_text) <= self.max_translation_block_size():
                    translated = BeautifulSoup(self._translate_xml(src_text, from_lang, to_lang, cache), 'html.parser')
                    strip_soup_text(translated)
                    cache[src_text] = str(translated)
                else:
                    arr = []
                    for piece in src_soup.children:
                        translated = BeautifulSoup(f'<div>{self._tran(piece, from_lang, to_lang, cache)}</div>',
                                                   'html.parser').div
                        strip_soup_text(translated)
                        arr.append(str(translated)[5:-6])
                    cache[src_text] = ''.join(arr)
            else:
                cache[src_text] = self._translate_xml(src_text, from_lang, to_lang, cache)
        return cache[src_text]

    def is_disabled(self) -> bool:
        raise NotImplementedError()

    def _translate_plain_text(self, src_text: str, from_lang: str, to_lang: str,
                              cache) -> Tuple[str, Union[BaseException, None]]:
        raise NotImplementedError()

    def _translate_xml(self, src_text, from_lang, to_lang, cache) -> str:
        raise NotImplementedError()

    def _pre_check(self, src_text: str, from_lang: str, to_lang: str, is_plain_str: bool) -> Union[BaseException, None]:
        raise NotImplementedError()

    @staticmethod
    def max_translation_block_size() -> int:
        raise NotImplementedError()

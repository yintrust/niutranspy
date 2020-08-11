import json
import logging
import threading
from itertools import count
from time import sleep
from typing import Tuple

import cld3
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from sqlitedict import SqliteDict

from niutranspy.constants import _INLINE_ELEMENTS

_caches = {}
_old_caches = {}
_log = logging.getLogger(__name__)
_lock = threading.RLock()


def get_text_contents(soup) -> str:
    """Get plain text in BeautifulSoup object.

    :param soup: BeautifulSoup object.
    :return: Text string.
    """
    if not soup: return ''  # noqa: E701
    text = soup if (isinstance(soup, NavigableString) or isinstance(soup, str)) else soup.text
    return ' '.join(text.replace('\\r\\n', ' ').strip().split())


def html_to_text(html_str: str) -> str:
    """Convert HTML to plain text without HTML tags.

    :param html_str: HTML string.
    :return: Text string.
    """
    return get_text_contents(BeautifulSoup(html_str, 'html.parser'))


def _load_dict(filename, from_lang, to_lang, cache_name):
    dic = cache_name.setdefault(filename, {}).setdefault((from_lang, to_lang), {})
    if not dic:
        for k, v in SqliteDict(filename=filename, tablename='{}_{}'.format(from_lang, to_lang), autocommit=False,
                               encode=json.dumps, decode=json.loads).items():
            dic[k] = v
        _log.info(f'Loaded {len(dic)} items')
    return dic


def _load_dicts(filename, from_lang, to_lang):
    with _lock:
        return _load_dict(filename, from_lang, to_lang, _caches), _load_dict(filename + '.bak', from_lang, to_lang,
                                                                             _old_caches)


def get_lang(s: str, proportion: float = 0.8) -> Tuple[bool, str]:
    """Returns the most likely language detected by cld3.

    :param s: String to be detected.
    :param proportion: Proportion.
    :return: e.g. ``(True, 'en')``
    """
    # get_language() is not so reliable: mixed languages content is not well detected
    r = cld3.get_frequent_languages(s, 3)[0]
    return r.is_reliable and r.proportion > proportion, r.language


def _try_despite_of_errors(req_func, exception_classes, times: int = 4):
    """Returns the req_func() despite of at most ``times`` requests connection errors.
    :param req_func: Requests function.
    :param exception_classes: Exception classes.
    :param times: Maximum number of times.
    :return: ``req_func``
    """
    assert times > 0
    for i in count(1):
        try:
            return req_func()
        except exception_classes as e:
            if i > times:
                _log.fatal(f'Max attempts failed to reach the translation server: {str(e)}')
                raise
            sleep(10 * i)


def _inline_sibling(n: Tag) -> bool:
    return n and n.name in _INLINE_ELEMENTS


def strip_soup_text(soup) -> None:
    """Strip a BeautifulSoup soup piece's inline elements.

    Ref: https://medium.com/@patrickbrosset/when-does-white-space-matter-in-html-b90e8a7cdd33
    Ref: https://www.ruanyifeng.com/blog/2018/07/white-space.html
    """
    todo = []
    for sub in soup.descendants:
        if not isinstance(sub, NavigableString):
            # assert sub.name != 'pre', str(sub)
            continue

        lo = hi = ''
        new_sub = get_text_contents(sub)
        edge = False
        if sub:
            prv = _inline_sibling(sub.previous_sibling)
            nxt = _inline_sibling(sub.next_sibling)
            edge = not (prv and nxt)
            if sub[0].isspace() and prv: lo = ' '  # noqa: E701
            if sub[-1].isspace() and (new_sub or not lo) and nxt:
                hi = ' '
        if edge and not new_sub: lo = hi = ''  # noqa: E701
        todo.append((sub, ''.join((lo, new_sub, hi))))

    for sub, s in todo:
        if s:
            sub.replace_with(s)
        else:
            sub.extract()

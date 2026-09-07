import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from private_console import _content_disposition


class PrivateConsoleTests(unittest.TestCase):
    def test_unicode_download_name_uses_ascii_safe_rfc5987_header(self):
        value=_content_disposition('逆さの茶笠 - 번역본.txt')
        value.encode('latin-1')
        self.assertIn("filename*=UTF-8''",value)
        self.assertIn('%E9%80%86',value)
        self.assertIn('%EB%B2%88%EC%97%AD%EB%B3%B8.txt',value)


if __name__=='__main__':unittest.main()

import pytest

from laya.config import Settings
from laya.core import Laya


@pytest.fixture
def laya(tmp_path):
    return Laya(Settings(data_dir=tmp_path, backend="mock"))

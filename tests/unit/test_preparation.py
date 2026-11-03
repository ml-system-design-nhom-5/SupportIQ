# tests/unit/test_preparation.py
import pytest

def test_data_science_packages_installed():
    import pandas as pd
    import numpy as np
    import sklearn
    import joblib
    import matplotlib
    assert pd.__version__ is not None
    assert np.__version__ is not None
    assert sklearn.__version__ is not None
    assert joblib.__version__ is not None
    assert matplotlib.__version__ is not None

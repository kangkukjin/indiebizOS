"""The model installer cannot replace executable data or escape its model directory."""
import io
import zipfile

import boot_paths  # noqa: F401
import hippocampus_provision as provision


def test_download_installs_only_model_files(tmp_path, monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('models/ibl_embedding/model.safetensors', b'model')
        z.writestr('models/ibl_embedding/config.json', '{}')
        z.writestr('ibl_usage.db', b'replacement')
        z.writestr('training/ibl_distilled.json', '["unqualified"]')
        z.writestr('models/ibl_embedding/../../escape', 'escape')
    data = tmp_path/'data'
    data.mkdir()
    (data/'ibl_usage.db').write_bytes(b'owned')
    monkeypatch.setattr(provision, '_base', lambda: tmp_path)
    monkeypatch.setattr(provision, 'urlopen', lambda *a, **k: io.BytesIO(archive.getvalue()))
    assert provision.download_model('https://example.invalid/model.zip')
    assert (data/'models/ibl_embedding/model.safetensors').read_bytes() == b'model'
    assert (data/'ibl_usage.db').read_bytes() == b'owned'
    assert not (data/'training').exists() and not (data/'escape').exists()
    monkeypatch.setattr(provision, 'urlopen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('already installed')))
    assert provision.download_model()


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))

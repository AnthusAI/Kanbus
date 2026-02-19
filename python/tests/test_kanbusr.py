from importlib import reload


def test_shim_imports_kanbus_version():
    # Ensure the compatibility shim exposes the same version symbol
    import kanbus
    import kanbusr

    assert kanbusr.__version__ == kanbus.__version__

    # Reload to touch the module body for coverage
    reloaded = reload(kanbusr)
    assert hasattr(reloaded, "__all__")

import pytest

from cortador.config import (JoineryOptions, LabelOptions, PrinterSpec,
                             SliceConfig, axis_index)


def test_axis_index():
    assert axis_index("x") == 0
    assert axis_index("Z") == 2
    assert axis_index(1) == 1
    with pytest.raises(ValueError):
        axis_index("w")


def test_printer_usable_y_fits():
    p = PrinterSpec(200, 200, 250, clearance=5)
    assert p.usable() == (190, 190, 240)
    assert p.fits([100, 100, 100])
    assert not p.fits([195, 10, 10])


def test_validacion():
    cfg = SliceConfig()
    cfg.validate()
    cfg.mode = "otro"
    with pytest.raises(ValueError):
        cfg.validate()
    with pytest.raises(ValueError):
        SliceConfig(slab_thickness=0).validate()
    with pytest.raises(ValueError):
        SliceConfig(kerf=-1).validate()


def test_ida_y_vuelta_dict():
    cfg = SliceConfig(printer=PrinterSpec(300, 200, 400, 2), mode="slabs",
                      slab_thickness=3.5,
                      labels=LabelOptions(style="emboss", size=6),
                      joinery=JoineryOptions(mode="pins", count=3))
    copia = SliceConfig.from_dict(cfg.to_dict())
    assert copia.printer.x == 300
    assert copia.slab_thickness == 3.5
    assert copia.labels.style == "emboss"
    assert copia.joinery.count == 3


def test_from_dict_ignora_campos_desconocidos():
    cfg = SliceConfig.from_dict({"mode": "slabs", "inventado": 5,
                                 "printer": {"x": 100, "raro": 1}})
    assert cfg.mode == "slabs"
    assert cfg.printer.x == 100

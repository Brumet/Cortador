import numpy as np
import pytest
import trimesh


@pytest.fixture(scope="session")
def esfera():
    return trimesh.creation.icosphere(subdivisions=3, radius=50.0)


@pytest.fixture(scope="session")
def caja():
    m = trimesh.creation.box(extents=[120.0, 80.0, 200.0])
    m.apply_translation([60.0, 40.0, 100.0])
    return m


@pytest.fixture(scope="session")
def figura():
    """Varios cuerpos superpuestos: el caso tipico de un modelo descargado."""
    parts = [trimesh.creation.box(extents=[80, 60, 200])]
    parts[0].apply_translation([0, 0, 100])
    ball = trimesh.creation.icosphere(subdivisions=2, radius=55)
    ball.apply_translation([0, 0, 210])
    parts.append(ball)
    arm = trimesh.creation.cylinder(radius=18, height=160, sections=16)
    arm.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    arm.apply_translation([0, 0, 150])
    parts.append(arm)
    mesh = trimesh.util.concatenate(parts)
    mesh.apply_translation(-mesh.bounds[0])
    return mesh

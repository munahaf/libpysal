"""

For completeness, we need to test a shuffled dataframe
(i.e. always send unsorted data) with:
- numeric ids
- string ids
- mixed polygon/multipolygon dataset
- mixed line/multiline dataset
- dataset with islands
"""

import pandas, geopandas, geodatasets, pytest, shapely, numpy
from libpysal.weights.experimental._contiguity import (
    _vertex_set_intersection,
    _rook,
    _queen,
)

numpy.random.seed(111211)
rivers = geopandas.read_file(geodatasets.get_path("eea large_rivers")).sample(
    frac=1, replace=False
)
rivers["strID"] = rivers.NAME
rivers["intID"] = rivers.index.values + 2

nybb = geopandas.read_file(geodatasets.get_path("ny bb"))
nybb["strID"] = nybb.BoroName
nybb["intID"] = nybb.BoroCode

parametrize_ids = pytest.mark.parametrize("ids", [None, "strID", "intID"])
parametrize_geoms = pytest.mark.parametrize("geoms", [rivers, nybb], ["rivers", "nybb"])
parametrize_perim = pytest.mark.parametrize(
    "by_perimeter", [False, True], ids=["binary", "perimeter"]
)
parametrize_rook = pytest.mark.parametrize("rook", [True, False], ids=["rook", "queen"])
parametrize_pointset = pytest.mark.parametrize(
    "pointset", [True, False], ids=["pointset", "vertex intersection"]
)

@parametrize_pointset
@parametrize_rook
@parametrize_ids
def test_user_rivers(ids, rook, pointset, data=rivers):
    data = data.reset_index(drop=False, names='original_index')
    ids = 'original_index' if ids is None else ids
    data = data.set_index(ids, drop=False)
    ids = data.index.values
    # implement known_heads, known_tails

    if rook:
        known_heads = known_tails = ids[numpy.arange(len(data))]
        known_weights = numpy.zeros_like(known_heads)
    else:
        known_heads = numpy.array(["Sava", "Danube", "Tisa", "Danube"])
        known_tails = numpy.array(["Danube", "Sava", "Danube", "Tisa"])
        isolates = data[~data.strID.isin(known_heads)].index.values

        tmp_ = data.reset_index(names="tmp_index").set_index("strID")

        known_heads = tmp_.loc[known_heads, "tmp_index"].values
        known_tails = tmp_.loc[known_tails, "tmp_index"].values

        known_heads = numpy.hstack((known_heads, isolates))
        known_tails = numpy.hstack((known_tails, isolates))

        known_weights = numpy.ones_like(known_heads)
        known_weights[known_heads == known_tails] = 0
    if pointset:
        f = _rook if rook else _queen
        derived = f(data, ids=ids)
    else:
        derived = _vertex_set_intersection(data, ids=ids, rook=rook)

    assert set(zip(*derived)) == set(zip(known_heads, known_tails, known_weights))


@parametrize_rook
@parametrize_perim
@parametrize_ids
def test_user_vertex_set_intersection_nybb(ids, rook, by_perimeter, data=nybb):
    if ids is not None:
        data = data.set_index(ids, drop=False)
    ids = data.index.values
    # implement known_heads, known_tails
    known_heads = numpy.array([1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 0])
    known_tails = numpy.array([2, 3, 4, 1, 3, 2, 1, 4, 1, 3, 0])

    known_heads = data.index.values[known_heads]
    known_tails = data.index.values[known_tails]

    if by_perimeter:
        head_geom = data.geometry.loc[known_heads].values
        tail_geom = data.geometry.loc[known_tails].values
        known_weights = head_geom.intersection(tail_geom).length
    else:
        known_weights = numpy.ones_like(known_heads)
    known_weights[known_heads == known_tails] = 0

    f = _rook if rook else _queen
    derived = f(data, by_perimeter=by_perimeter, ids=ids)

    assert set(zip(*derived)) == set(zip(known_heads, known_tails, known_weights))


@parametrize_rook
@parametrize_perim
@parametrize_ids
def test_user_pointset_nybb(ids, by_perimeter, rook, data=nybb):
    if ids is not None:
        data = data.set_index(ids, drop=False)
    ids = data.index.values
    # implement known_heads, known_tails
    known_heads = numpy.array([1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 0])
    known_tails = numpy.array([2, 3, 4, 1, 3, 2, 1, 4, 1, 3, 0])

    known_heads = data.index.values[known_heads]
    known_tails = data.index.values[known_tails]

    if by_perimeter:
        head_geom = data.geometry.loc[known_heads].values
        tail_geom = data.geometry.loc[known_tails].values
        known_weights = head_geom.intersection(tail_geom).length
    else:
        known_weights = numpy.ones_like(known_heads)
    known_weights[known_heads == known_tails] = 0

    f = _rook if rook else _queen
    derived = f(data, by_perimeter=by_perimeter, ids=ids)

    assert set(zip(*derived)) == set(zip(known_heads, known_tails, known_weights))


@parametrize_pointset
def test_correctness_rook_queen_distinct(pointset):
    """
    Check that queen and rook generate different contiguities in the case of a
    shared point but no edge.
    """
    data = geopandas.GeoSeries((shapely.box(0, 0, 1, 1), shapely.box(1, 1, 2, 2)))
    if pointset:
        rook_ = _rook(data.geometry)
        queen_ = _queen(data.geometry)

    else:
        rook_ = _vertex_set_intersection(data.geometry, rook=True)
        queen_ = _vertex_set_intersection(data.geometry, rook=False)

    with pytest.raises(AssertionError):
        assert set(zip(*rook_)) == set(zip(*queen_))


def test_correctness_vertex_set_contiguity_distinct():
    """
    Check to ensure that vertex set ignores rook/queen neighbors that share
    an edge whose nodes are *not* in the vertex set. The test case is two
    offset squares
    """
    data = geopandas.GeoSeries((shapely.box(0, 0, 1, 1), shapely.box(0.5, 1, 1.5, 2)))

    vs_rook = _vertex_set_intersection(data, rook=True)

    rook = _rook(data)

    with pytest.raises(AssertionError):
        assert set(zip(*vs_rook)) == set(zip(*rook))

    vs_queen = _vertex_set_intersection(data, rook=False)

    queen = _queen(data)

    with pytest.raises(AssertionError):
        assert set(zip(*vs_queen)) == set(zip(*queen))

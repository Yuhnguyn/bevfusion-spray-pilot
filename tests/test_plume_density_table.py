import scripts.plume_density_table as density_table


def test_density_table_has_all_seeds_and_totals_grow():
    rows = density_table.build_rows()

    assert len(rows) == len(density_table.SEEDS) == 5
    assert all(row["after"] > row["before"] for row in rows)
    assert all(row["clusters"] > 0 for row in rows)

    total = density_table.totals(rows)
    assert total["after"] >= total["before"]


def test_density_table_render_marks_legacy_table(capsys):
    density_table.main()

    out = capsys.readouterr().out
    assert "điểm trước" in out and "điểm sau" in out
    assert "công thức trước ticket 21–22" in out
    assert "1.330 → 1.057" in out

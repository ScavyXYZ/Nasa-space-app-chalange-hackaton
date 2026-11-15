"""Separate graph-search success from physical traversability verification."""


def traversability_assessment(spacing_m, *, global_model):
    return {
        "status": "unverified",
        "scope": "strategic_corridor" if global_model else "local_dem_path",
        "dem_spacing_m": spacing_m,
        "terrain_constraints_checked": ["cell_to_cell_gradient"] if global_model else [
            "cell_to_cell_gradient", "surface_slope", "diagonal_corner_clearance"],
        "missing_evidence": ["local_crater_rims_and_cliffs", "boulders", "soil_traction"]
                            if global_model else ["boulders", "soil_traction"],
        "message": (
            "Лише стратегічний напрямок — прохідність не перевірена. "
            "Глобальна DEM не розрізняє локальні борти кратерів, уступи й каміння. "
            "Лінія може перетинати непроїзні ділянки; для ровера потрібна детальна перевірка."
            if global_model else
            "Шлях перевірений лише за обмеженнями локальної DEM. "
            "Каміння, ґрунт і зчеплення не перевірені; фізична прохідність не підтверджена."
        ),
    }

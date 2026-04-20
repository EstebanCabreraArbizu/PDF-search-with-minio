def infer_domain_code(minio_object_name: str = "", tipo_documento: str = "") -> str:
    joined = f"{minio_object_name or ''} {tipo_documento or ''}".lower()
    if "tregistro" in joined or "t-registro" in joined:
        return "TREGISTRO"
    if (
        "sctr" in joined
        or "vida ley" in joined
        or "seguros" in joined
        or "poliza" in joined
    ):
        return "SEGUROS"
    return "CONSTANCIA_ABONO"

from calcucalo.services.evaluation import EvaluationAccumulator


def test_end_to_end_metrics_match_food_id_and_measure_numeric_error() -> None:
    accumulator = EvaluationAccumulator()
    accumulator.add_sample(
        expected=[
            {
                "food_id": "VN_COM_TAM",
                "weight_g": 400,
                "calories_kcal": 600,
                "protein_g": 30,
            },
            {"food_id": "VN_CANH", "weight_g": 300},
        ],
        predicted=[
            {
                "food_id": "VN_COM_TAM",
                "estimated_portion_g": 380,
                "estimated_totals": {
                    "calories_kcal": 570,
                    "protein_g": 27,
                    "fat_g": 20,
                    "carb_g": 70,
                },
            },
            {
                "food_id": "VN_DAU_HU",
                "estimated_portion_g": 100,
                "estimated_totals": {},
            },
        ],
    )

    report = accumulator.report()

    assert report["food_detection"] == {
        "expected": 2,
        "predicted": 2,
        "matched": 1,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
    assert report["errors"]["weight_g"]["mae"] == 20.0
    assert report["errors"]["weight_g"]["mape_percent"] == 5.0
    assert report["errors"]["calories_kcal"]["mae"] == 30.0
    assert report["errors"]["protein_g"]["mae"] == 3.0
    assert report["errors"]["fat_g"]["count"] == 0


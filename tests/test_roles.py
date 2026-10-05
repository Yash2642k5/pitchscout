from app.roles import classify_title, role_mix


def test_ml_and_research_keywords():
    assert classify_title("Senior Machine Learning Engineer") == "ML and research"
    assert classify_title("Data Scientist") == "ML and research"
    assert classify_title("NLP Research Scientist") == "ML and research"
    assert classify_title("AI Researcher") == "ML and research"


def test_ml_and_research_wins_over_engineering_when_both_present():
    # "ML and research" is checked first, so "Machine Learning Engineer" matches it, not Engineering.
    assert classify_title("Machine Learning Engineer") == "ML and research"


def test_engineering_keywords():
    assert classify_title("Backend Engineer") == "Engineering"
    assert classify_title("DevOps Engineer") == "Engineering"
    assert classify_title("Full Stack Developer") == "Engineering"
    assert classify_title("Site Reliability Engineer (SRE)") == "Engineering"


def test_sales_and_marketing_keywords():
    assert classify_title("Account Executive, Enterprise") == "Sales and marketing"
    assert classify_title("Growth Marketing Lead") == "Sales and marketing"
    assert classify_title("Customer Success Manager") == "Sales and marketing"
    assert classify_title("Business Development Representative") == "Sales and marketing"


def test_other_bucket():
    assert classify_title("Office Manager") == "Other"
    assert classify_title("Executive Assistant") == "Other"


def test_whole_word_matching_does_not_false_positive():
    # "ai" should not match inside unrelated words like "maintain" or "said".
    assert classify_title("Facilities Maintenance Technician") == "Other"
    assert classify_title("Public Relations Said Spokesperson") == "Other"


def test_case_insensitive():
    assert classify_title("SENIOR MACHINE LEARNING ENGINEER") == "ML and research"


def test_data_scien_matches_as_prefix():
    assert classify_title("Lead Data Scientist") == "ML and research"
    assert classify_title("Data Science Manager") == "ML and research"


def test_role_mix_counts_each_function():
    titles = [
        "Senior Machine Learning Engineer",
        "Backend Engineer",
        "Account Executive, Enterprise",
        "Research Scientist, NLP",
        "Customer Success Manager",
    ]
    counts = role_mix(titles)
    assert counts == {
        "ML and research": 2,
        "Engineering": 1,
        "Sales and marketing": 2,
        "Other": 0,
    }

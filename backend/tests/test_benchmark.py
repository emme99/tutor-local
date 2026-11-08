import run_llm_bench


def test_benchmark_cache_key_is_stable_and_sensitive_to_config():
    cfg = {"base_url": "http://localhost:11434/v1", "model": "gemma4:26b"}
    case = {"id": "x", "text": "I am agree with you."}
    first = run_llm_bench.key_for(cfg, case)
    assert first == run_llm_bench.key_for(dict(cfg), dict(case))

    changed_prompt = dict(cfg, model="other")
    assert first != run_llm_bench.key_for(changed_prompt, case)

    changed_case = dict(case, text="I agree with you.")
    assert first != run_llm_bench.key_for(cfg, changed_case)

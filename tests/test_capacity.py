"""ทดสอบตัวประเมินขีดจำกัดการรัน MuMu (estimate_mumu_capacity)"""
from mumu_controller import estimate_mumu_capacity, DEFAULT_MUMU_PROFILE


def _specs(logical, total, avail):
    return {
        "available_ok": True,
        "logical_cores": logical,
        "physical_cores": logical // 2,
        "total_ram_gb": total,
        "available_ram_gb": avail,
    }


def test_default_profile_values():
    assert DEFAULT_MUMU_PROFILE["ram_per_instance_gb"] == 3.0
    assert DEFAULT_MUMU_PROFILE["cores_per_instance"] == 2


def test_typical_16gb_8core():
    # 16GB/8core: RAM (16-2.5)/3=4, CPU (8-2)*1.5/2=4 -> แนะนำ 4
    est = estimate_mumu_capacity(_specs(8, 16, 8))
    assert est["ram_limit"] == 4
    assert est["cpu_limit"] == 4
    assert est["recommended"] == 4


def test_ram_is_bottleneck_low_ram_many_cores():
    # 8GB/16core: RAM (8-2.5)/3=1, CPU (16-2)*1.5/2=10 -> คอขวด RAM, แนะนำ 1
    est = estimate_mumu_capacity(_specs(16, 8, 8))
    assert est["ram_limit"] == 1
    assert est["recommended"] == 1
    assert est["bottleneck"] == "RAM"


def test_cpu_is_bottleneck_high_ram_few_cores():
    # 32GB/4core: RAM (32-2.5)/3=9, CPU (4-2)*1.5/2=1 -> คอขวด CPU, แนะนำ 1
    est = estimate_mumu_capacity(_specs(4, 32, 32))
    assert est["cpu_limit"] == 1
    assert est["recommended"] == 1
    assert est["bottleneck"] == "CPU"


def test_open_now_capped_by_available_ram():
    # RAM ว่างตอนนี้ 3.4GB -> (3.4-0.5)/3 = 0 จอ แม้เพดานแนะนำจะมากกว่า
    est = estimate_mumu_capacity(_specs(8, 16, 3.4))
    assert est["open_now"] == 0
    assert est["recommended"] >= 1


def test_open_now_never_exceeds_recommended():
    est = estimate_mumu_capacity(_specs(8, 64, 64))
    assert est["open_now"] <= est["recommended"]


def test_too_weak_machine_returns_zero():
    # 2GB รวม -> กันระบบ 2.5GB ติดลบ -> 0 จอ
    est = estimate_mumu_capacity(_specs(2, 2, 1))
    assert est["recommended"] == 0


def test_custom_profile_override():
    # ลด RAM/จอ เป็น 2GB -> เปิดได้มากขึ้น
    est = estimate_mumu_capacity(_specs(8, 16, 16), profile={"ram_per_instance_gb": 2.0})
    assert est["ram_limit"] == int((16 - 2.5) // 2.0)

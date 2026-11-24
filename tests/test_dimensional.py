"""Unit tests for dimensional analysis in SI and natural units."""

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.equations.dimensional import check_dimensional_analysis


def test_einstein_mass_energy_si():
    equation = "E = m * c**2"
    units = {
        "E": "joule",
        "m": "kilogram",
        "c": "meter / second",
    }
    res = check_dimensional_analysis(equation, units, unit_system="SI")
    assert res.status == VerificationStatus.VERIFIED
    assert "Dimensionally consistent" in res.summary


def test_kinematics_multiterm_consistent():
    equation = "s = u * t + 0.5 * a * t**2"
    units = {
        "s": "meter",
        "u": "meter / second",
        "t": "second",
        "a": "meter / second**2",
    }
    res = check_dimensional_analysis(equation, units, unit_system="SI")
    assert res.status == VerificationStatus.VERIFIED


def test_inconsistent_additive_terms():
    # s = v*t + a*t (a*t has dimension of velocity, not distance)
    equation = "s = u * t + a * t"
    units = {
        "s": "meter",
        "u": "meter / second",
        "t": "second",
        "a": "meter / second**2",
    }
    res = check_dimensional_analysis(equation, units, unit_system="SI")
    assert res.status == VerificationStatus.FAILED
    assert "inconsistency" in res.summary.lower()


def test_materials_science_units():
    # Stress sigma = F / A, checked against GPa
    equation = "sigma = F / A"
    units = {
        "sigma": "gigapascal",
        "F": "newton",
        "A": "meter**2",
    }
    res = check_dimensional_analysis(equation, units, unit_system="SI")
    assert res.status == VerificationStatus.VERIFIED


def test_natural_units_energy_mass():
    # In natural units (hbar = c = 1), E and m have identical energy dimensions D = 1
    equation = "E = m"
    units = {
        "E": "joule",
        "m": "kilogram",
    }
    res = check_dimensional_analysis(equation, units, unit_system="natural")
    assert res.status == VerificationStatus.VERIFIED
    assert res.details["energy_mass_dimension"] == 1


def test_natural_units_mismatch():
    # In natural units, action S (dimensionless D=0) != energy E (D=1)
    equation = "S = E"
    units = {
        "S": "joule * second",  # action dimension
        "E": "joule",
    }
    res = check_dimensional_analysis(equation, units, unit_system="natural")
    assert res.status == VerificationStatus.FAILED
    assert "Dimensional mismatch in natural units" in res.summary

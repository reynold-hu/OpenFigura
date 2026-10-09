import math
import pytest
from openfigura.core.skin_quality import analyze_weights

FAMILIES={'hand':['hand','finger'],'leg':['thigh','knee']}
PAIRS=[('hand','leg')]

def check(rows,**kw):return analyze_weights(rows,FAMILIES,PAIRS,**kw)

def test_cross_family_mass_detected_without_dominant_label_guessing():
    r=check([{'thigh':.3,'finger':.54,'knee':.16},{'hand':1}])
    assert r['assessment']=='suspicious'
    assert r['conflicts'][0]['vertices']==1
    sample=r['conflicts'][0]['samples'][0]
    assert sample['vertex']==0 and sample['mass_a']==pytest.approx(.54) and sample['mass_b']==pytest.approx(.46)
    assert r['skin_quality_accepted'] is False and r['collision_checked'] is False

def test_valid_rows_do_not_become_quality_pass():
    r=check([{'hand':1},{'thigh':.5,'knee':.5}])
    assert r['assessment']=='no_flagged_conflicts'
    assert r['vertices']==2 and r['unweighted_vertices']==0
    assert 'pass' not in r['assessment'] and not r['skin_quality_accepted']

def test_bad_rows_are_counted_not_hidden_by_normalization():
    r=check([{}, {'hand':0}, {'hand':.6}, {'hand':-1,'thigh':2}, {'hand':math.nan}, {'hand':math.inf}])
    assert r['assessment']=='invalid_weights'
    assert r['unweighted_vertices']==2
    assert r['negative_weight_vertices']==1
    assert r['nonfinite_weight_vertices']==2
    assert r['weight_sum_outside_tolerance_vertices']==1
    assert r['conflicts'][0]['vertices']==0

def test_conflict_threshold_is_strict_and_totals_aggregate_family():
    r=check([{'hand':.06,'finger':.06,'thigh':.88},{'hand':.1,'thigh':.9}])
    assert r['conflicts'][0]['vertices']==1

def test_streaming_inputs_and_sample_limit_still_count_all_conflicts():
    consumed=[]
    def rows():
        for i in range(10):consumed.append(i);yield {'hand':.5,'thigh':.5}
    r=check(rows(),sample_limit=2)
    assert len(consumed)==10 and r['vertices']==10
    assert r['conflicts'][0]['vertices']==10 and len(r['conflicts'][0]['samples'])==2

def test_unknown_positive_influences_reported_and_never_silently_classified():
    r=check([{'unknown':1},{'unknown':.5,'hand':.5}])
    assert r['unmapped_positive_weight_vertices']==2
    assert r['unmapped_bone_names']==['unknown']

@pytest.mark.parametrize('families,pairs',[({},PAIRS),({'a':['x'],'b':['x']},[('a','b')]),(FAMILIES,[('hand','hand')]),(FAMILIES,[('hand','missing')]),(FAMILIES,[]),(FAMILIES,[('hand','leg'),('leg','hand')])])
def test_invalid_semantic_config_refused(families,pairs):
    with pytest.raises(ValueError):analyze_weights([],families,pairs)

@pytest.mark.parametrize('params',[{'mass_threshold':True},{'mass_threshold':float('nan')},{'mass_threshold':-.1},{'mass_threshold':.5},{'sample_limit':True},{'sample_limit':-1},{'sum_tolerance':float('inf')}])
def test_invalid_diagnostic_parameters(params):
    with pytest.raises(ValueError):check([],**params)

@pytest.mark.parametrize('row',[None,{'hand':'1'},{'hand':True},{'':1},{1:1}])
def test_malformed_weight_records_refused(row):
    with pytest.raises(ValueError):check([row])

def test_empty_stream_does_not_get_a_clean_assessment():
    r=check([])
    assert r['assessment']=='unavailable' and not r['skin_quality_accepted']

def test_zero_sample_budget_reports_full_count():
    r=check([{'hand':.5,'thigh':.5}],sample_limit=0)
    assert r['conflicts'][0]['vertices']==1 and r['conflicts'][0]['samples']==[]

def test_input_weights_and_semantic_config_are_not_changed():
    import copy
    rows=[{'hand':.4,'thigh':.6}];before=copy.deepcopy((rows,FAMILIES,PAIRS))
    check(rows)
    assert (rows,FAMILIES,PAIRS)==before

def test_aggregate_overflow_is_invalid_not_a_clean_result():
    r=check([{'hand':1e308,'finger':1e308}])
    assert r['assessment']=='invalid_weights' and r['nonfinite_weight_vertices']==1

def test_unrepresentable_integer_weight_is_reported_without_crashing():
    r=check([{'hand':10**400}])
    assert r['assessment']=='invalid_weights' and r['nonfinite_weight_vertices']==1

@pytest.mark.parametrize('params',[{'mass_threshold':10**400},{'sum_tolerance':10**400}])
def test_unrepresentable_numeric_parameters_are_rejected_consistently(params):
    with pytest.raises(ValueError):check([],**params)

def test_report_exposes_coverage_when_defective_rows_are_skipped():
    r=check([{'hand':-.1,'thigh':.2},{'hand':math.nan,'unknown':1},{'hand':1}])
    assert r['conflict_checked_vertices']==1
    assert r['nonnegative_finite_weight_sum_checked_vertices']==1

"""Read-only weight diagnostics with explicit semantic families.

This kernel neither normalizes nor repairs weights. No finding is a skin,
deformation, or collision acceptance verdict. Bone families are caller supplied.
"""
import math
from numbers import Real


def _finite(value):
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError, TypeError):
        return False


def analyze_weights(rows, families, pairs, *, mass_threshold=.1,
                    sum_tolerance=1e-4, sample_limit=20):
    """Consume vertex weight dictionaries once, retain bounded conflict examples.

    ``pairs`` names family combinations to flag when both positive masses are
    strictly above the threshold. Caller must independently verify semantics.
    Vertex IDs in examples are the zero-based order of the supplied records.
    """
    for name, value in [('mass_threshold', mass_threshold), ('sum_tolerance', sum_tolerance)]:
        if isinstance(value, bool) or not isinstance(value, Real) or not _finite(value):
            raise ValueError(name+' must be a finite number')
    if not 0 <= mass_threshold < .5 or not 0 <= sum_tolerance < 1:
        raise ValueError('invalid threshold or sum tolerance')
    if type(sample_limit) is not int or not 0 <= sample_limit <= 1000:
        raise ValueError('sample_limit must be an integer in [0,1000]')
    if not isinstance(families, dict) or not families:
        raise ValueError('explicit nonempty bone families required')
    membership = {}
    for family, names in families.items():
        if not isinstance(family, str) or not family or not isinstance(names, (list,tuple)) or not names:
            raise ValueError('families need names and nonempty bone lists')
        for name in names:
            if not isinstance(name, str) or not name or name in membership:
                raise ValueError('bone family names must be nonempty and disjoint')
            membership[name] = family
    if not isinstance(pairs, (list,tuple)) or not pairs:
        raise ValueError('nonempty explicit family pairs required')
    seen = set(); conflicts = []
    for pair in pairs:
        if not isinstance(pair, (list,tuple)) or len(pair) != 2 or any(not isinstance(n,str) or n not in families for n in pair) or pair[0] == pair[1]:
            raise ValueError('pairs must refer to distinct configured families')
        key = frozenset(pair)
        if key in seen:
            raise ValueError('duplicate family pair')
        seen.add(key)
        conflicts.append({'family_a':pair[0], 'family_b':pair[1], 'vertices':0, 'samples':[]})
    result = {'vertices':0, 'unweighted_vertices':0, 'negative_weight_vertices':0,
              'nonfinite_weight_vertices':0, 'weight_sum_outside_tolerance_vertices':0,
              'unmapped_positive_weight_vertices':0, 'unmapped_bone_names':[],
              'conflict_checked_vertices':0, 'nonnegative_finite_weight_sum_checked_vertices':0,
              'conflicts':conflicts, 'mass_threshold':float(mass_threshold),
              'sum_tolerance':float(sum_tolerance), 'sample_limit':sample_limit,
              'skin_quality_accepted':False, 'collision_checked':False,
              'limitations':['caller-supplied families are not semantic ground truth',
                             'weight diagnostics only; no deformation or geometry checks',
                             'negative/nonfinite rows excluded from sum, unmapped and conflict checks; zero mass counted separately',
                             'unmapped influences are not covered by conflict rules']}
    unknown = set()
    for vertex, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('each vertex needs a bone-to-weight dictionary')
        for name, weight in row.items():
            if not isinstance(name,str) or not name or isinstance(weight,bool) or not isinstance(weight,Real):
                raise ValueError('invalid bone name or numeric weight')
        result['vertices'] += 1
        finite = all(_finite(w) for w in row.values())
        negative = any(w < 0 for w in row.values())
        result['negative_weight_vertices'] += int(negative)
        if not finite:
            result['nonfinite_weight_vertices'] += 1
            continue
        if negative:
            continue
        try:
            total = math.fsum(row.values())
        except OverflowError:
            result['nonfinite_weight_vertices'] += 1
            continue
        if not math.isfinite(total):
            result['nonfinite_weight_vertices'] += 1
            continue
        result['nonnegative_finite_weight_sum_checked_vertices'] += 1
        if total == 0:
            result['unweighted_vertices'] += 1
            continue
        if abs(total-1) > sum_tolerance:
            result['weight_sum_outside_tolerance_vertices'] += 1
        mass = {n:0.0 for n in families}; unmapped = False
        result['conflict_checked_vertices'] += 1
        for name, weight in row.items():
            if name in membership:
                mass[membership[name]] += weight
            elif weight > 0:
                unknown.add(name); unmapped = True
        result['unmapped_positive_weight_vertices'] += int(unmapped)
        for conflict in conflicts:
            a, b = mass[conflict['family_a']], mass[conflict['family_b']]
            if a > mass_threshold and b > mass_threshold:
                conflict['vertices'] += 1
                if len(conflict['samples']) < sample_limit:
                    conflict['samples'].append({'vertex':vertex, 'mass_a':float(a), 'mass_b':float(b)})
    result['unmapped_bone_names'] = sorted(unknown)
    invalid = any(result[name] for name in ['unweighted_vertices','negative_weight_vertices',
                   'nonfinite_weight_vertices','weight_sum_outside_tolerance_vertices'])
    result['assessment'] = ('unavailable' if not result['vertices'] else 'invalid_weights' if invalid
                            else 'suspicious' if any(c['vertices'] for c in conflicts)
                            else 'no_flagged_conflicts')
    return result

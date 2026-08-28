"""Tests for update_yaml, the writer behind PUT /config/set.

The delete path is what these mostly cover. `update_yaml` treats an empty-string
value as "remove this key", which is how every settings form clears a field --
notably the per-camera override editor in Settings -> Cameras -> Recording,
whose "Use global" control has to remove a key that may or may not be present.
"""

import unittest

from frigate.util.builtin import update_yaml, update_yaml_file_bulk  # noqa: F401


class TestUpdateYamlSet(unittest.TestCase):
    def test_sets_a_nested_value_creating_parents(self):
        data = {"cameras": {"Road01": {}}}
        update_yaml(
            data, ["cameras", "Road01", "record", "alerts", "retain", "days"], 90
        )
        assert data == {
            "cameras": {"Road01": {"record": {"alerts": {"retain": {"days": 90}}}}}
        }

    def test_overwrites_an_existing_value(self):
        data = {"cameras": {"Road01": {"record": {"alerts": {"retain": {"days": 90}}}}}}
        update_yaml(
            data, ["cameras", "Road01", "record", "alerts", "retain", "days"], 45
        )
        assert data["cameras"]["Road01"]["record"]["alerts"]["retain"]["days"] == 45

    def test_zero_is_a_value_not_a_delete(self):
        """0 == "" is False in Python, but the distinction matters enough to pin:
        a retention window of 0 days must be written, not treated as a removal."""
        data = {"record": {"motion": {"days": 7}}}
        update_yaml(data, ["record", "motion", "days"], 0)
        assert data == {"record": {"motion": {"days": 0}}}

    def test_false_is_a_value_not_a_delete(self):
        data = {"record": {"enabled": True}}
        update_yaml(data, ["record", "enabled"], False)
        assert data == {"record": {"enabled": False}}

    def test_merges_into_an_existing_dict(self):
        data = {"record": {"alerts": {"retain": {"days": 30}}}}
        update_yaml(data, ["record", "alerts"], {"pre_capture": 5})
        assert data["record"]["alerts"] == {"retain": {"days": 30}, "pre_capture": 5}


class TestUpdateYamlDelete(unittest.TestCase):
    def test_deletes_an_existing_key(self):
        data = {"record": {"alerts": {"retain": {"days": 90, "mode": "all"}}}}
        update_yaml(data, ["record", "alerts", "retain", "days"], "")
        assert data == {"record": {"alerts": {"retain": {"mode": "all"}}}}

    def test_deleting_a_missing_key_is_a_no_op(self):
        """Regression: this used to raise KeyError *after* creating the parent
        maps on the way down, so clearing a never-set override failed the whole
        save and left `record: {alerts: {retain: {}}}` husks behind."""
        data = {"cameras": {"Road01": {"enabled": True}}}
        update_yaml(
            data, ["cameras", "Road01", "record", "alerts", "retain", "days"], ""
        )
        assert data == {"cameras": {"Road01": {"enabled": True}}}

    def test_deleting_a_missing_key_creates_nothing(self):
        data = {}
        update_yaml(data, ["a", "b", "c"], "")
        assert data == {}

    def test_prunes_maps_the_delete_emptied(self):
        data = {
            "cameras": {
                "Road01": {
                    "enabled": True,
                    "record": {"alerts": {"retain": {"days": 90}}},
                }
            }
        }
        update_yaml(
            data, ["cameras", "Road01", "record", "alerts", "retain", "days"], ""
        )
        assert data == {"cameras": {"Road01": {"enabled": True}}}

    def test_pruning_stops_at_a_non_empty_map(self):
        data = {
            "cameras": {
                "Road01": {
                    "record": {"alerts": {"retain": {"days": 90, "mode": "all"}}}
                }
            }
        }
        update_yaml(
            data, ["cameras", "Road01", "record", "alerts", "retain", "days"], ""
        )
        assert data == {
            "cameras": {"Road01": {"record": {"alerts": {"retain": {"mode": "all"}}}}}
        }

    def test_pruning_leaves_unrelated_siblings_alone(self):
        data = {"a": {"b": {"c": 1}}, "keep": 2}
        update_yaml(data, ["a", "b", "c"], "")
        assert data == {"keep": 2}

    def test_deletes_a_list_entry_by_index(self):
        data = {"violations": [{"name": "one"}, {"name": "two"}]}
        update_yaml(data, [("violations", 1)], "")
        assert data == {"violations": [{"name": "one"}]}

    def test_deleting_an_out_of_range_index_is_a_no_op(self):
        data = {"violations": [{"name": "one"}]}
        update_yaml(data, [("violations", 5)], "")
        assert data == {"violations": [{"name": "one"}]}


if __name__ == "__main__":
    unittest.main(verbosity=2)

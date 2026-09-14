import os

from agent_nexus_cli.postgres_pipeline import rss_bytes
from agent_nexus_cli.process_tree import descendants, parents


def test_descendants_excludes_unrelated_processes_and_handles_cycles():
    assert descendants({2: 1, 3: 2, 4: 9, 5: 3}, {1}) == {1, 2, 3, 5}
    assert descendants({1: 2, 2: 1, 3: 9}, {1}) == {1, 2}
    assert descendants({1: 0}, set()) == set()


def test_local_process_sampling():
    mapping = parents()
    assert os.getpid() in mapping
    assert rss_bytes(os.getpid()) > 0

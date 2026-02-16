"""Domain registry for orchestrator runs."""

from orchestrator.domains.env_gridworld_v1 import DOMAIN_ID as ENV_GRIDWORLD_V1
from orchestrator.domains.env_gridworld_v1 import load_domain as load_env_gridworld_v1
from orchestrator.domains.io_algorithms_v1 import DOMAIN_ID as IO_ALGORITHMS_V1
from orchestrator.domains.io_algorithms_v1 import load_domain as load_io_algorithms_v1
from orchestrator.domains.python_ut_v1 import DOMAIN_ID as PYTHON_UT_V1
from orchestrator.domains.python_ut_v1 import load_domain as load_python_ut_v1

__all__ = [
    "ENV_GRIDWORLD_V1",
    "IO_ALGORITHMS_V1",
    "PYTHON_UT_V1",
    "load_env_gridworld_v1",
    "load_io_algorithms_v1",
    "load_python_ut_v1",
]

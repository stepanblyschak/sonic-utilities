import pytest
import fnmatch
import textwrap

from unittest.mock import patch, MagicMock
from show.main import cli
from click.testing import CliRunner


@pytest.fixture
def cfgdb():
    class DB(MagicMock):
        CONFIG_DB = "CONFIG_DB"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.dbs = {
                self.CONFIG_DB: {
                    "WARM_RESTART": {
                        "teamd": {
                            "teamsyncd_timer": "120",
                        },
                    },
                },
            }

        def get_table(self, table):
            return self.dbs[self.CONFIG_DB][table]

    with patch("show.warm_restart.ConfigDBConnector", return_value=DB()) as db:
        yield db


@pytest.fixture
def statedb():
    class DB(MagicMock):
        STATE_DB = "STATE_DB"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.dbs = {
                self.STATE_DB: {
                    "WARM_RESTART_TABLE|orchagent": {
                        "state": "restored",
                        "restore_count": "1"
                    },
                    "WARM_RESTART_TABLE|syncd": {
                        "state": "reconciled",
                        "restore_count": "1"
                    },
                    "WARM_RESTART_ENABLE_TABLE|system": {
                        "enable": "true",
                    },
                },
            }

        def keys(self, db, hash):
            return [key for key in self.dbs[db].keys() if fnmatch.fnmatch(key, hash)]

        def get(self, db, key, field):
            return self.dbs[db][key].get(field, None)

        def get_all(self, db, key):
            return self.dbs[db][key]

    with patch("show.warm_restart.SonicV2Connector", return_value=DB()) as db:
        yield db


@pytest.fixture
def multi_asic_mock():
    with patch("show.warm_restart.multi_asic_util.multi_asic_ns_choices", return_value=["asic1"]) as mock:
        yield mock


@pytest.mark.parametrize("namespace", [None, "asic1"])
def test_show_warm_restart(namespace, statedb, multi_asic_mock):
    runner = CliRunner()
    arguments = []
    if namespace:
        arguments += ["-n", namespace]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["state"], arguments,
    )
    namespace = namespace or ""
    statedb.assert_called_once_with(namespace=namespace)
    expected_output = textwrap.dedent("""\
        name         restore_count  state
        ---------  ---------------  ----------
        orchagent                1  restored
        syncd                    1  reconciled
    """)
    assert result.output == expected_output
    assert result.exit_code == 0


def test_show_warm_restart_unix_sock_usage(statedb, multi_asic_mock):
    runner = CliRunner()
    arguments = ["-s", "/var/run/redis/redis.sock"]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["state"], arguments,
    )
    expected_output = textwrap.dedent("""\
        Warning: '-s|--redis-unix-socket-path' has no effect and is left for compatibility
        name         restore_count  state
        ---------  ---------------  ----------
        orchagent                1  restored
        syncd                    1  reconciled
    """)
    assert result.output == expected_output
    assert result.exit_code == 0


def test_show_warm_restart_unix_sock_usage(statedb, multi_asic_mock):
    runner = CliRunner()
    arguments = ["-s", "/var/run/redis/redis.sock"]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["state"], arguments,
    )
    expected_output = textwrap.dedent("""\
        Warning: '-s|--redis-unix-socket-path' has no effect and is left for compatibility
        name         restore_count  state
        ---------  ---------------  ----------
        orchagent                1  restored
        syncd                    1  reconciled
    """)
    assert result.output == expected_output
    assert result.exit_code == 0


def test_show_warm_restart_invalid_namespace(statedb, multi_asic_mock):
    runner = CliRunner()
    arguments = ["-n", "asicX"]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["state"], arguments,
    )
    expected_output = textwrap.dedent("""\
        Usage: state [OPTIONS]

        Error: Invalid namespace: asicX
    """)
    assert result.output == expected_output
    assert result.exit_code == 2


@pytest.mark.parametrize("namespace", [None, "asic1"])
def test_show_warm_restart_config(namespace, statedb, cfgdb, multi_asic_mock):
    runner = CliRunner()
    arguments = []
    if namespace:
        arguments += ["-n", namespace]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["config"], arguments,
    )
    namespace = namespace or ""
    statedb.assert_called_once_with(namespace=namespace)
    cfgdb.assert_called_once_with(namespace=namespace)
    expected_output = textwrap.dedent("""\
        name    enable    timer_name       timer_duration    eoiu_enable
        ------  --------  ---------------  ----------------  -------------
        teamd   false     teamsyncd_timer  120               NULL
        system  true      NULL             NULL              NULL
    """)
    assert result.output == expected_output
    assert result.exit_code == 0


def test_show_warm_restart_config_invalid_namespace(statedb, cfgdb, multi_asic_mock):
    runner = CliRunner()
    arguments = ["-n", "asicX"]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["config"], arguments,
    )
    expected_output = textwrap.dedent("""\
        Usage: config [OPTIONS]

        Error: Invalid namespace: asicX
    """)
    assert result.output == expected_output
    assert result.exit_code == 2


def test_show_warm_restart_unix_sock_usage(statedb, cfgdb, multi_asic_mock):
    runner = CliRunner()
    arguments = ["-s", "/var/run/redis/redis.sock"]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["config"], arguments,
    )
    cfgdb.assert_called_once_with(namespace="",unix_socket_path="/var/run/redis/redis.sock")
    expected_output = textwrap.dedent("""\
        name    enable    timer_name       timer_duration    eoiu_enable
        ------  --------  ---------------  ----------------  -------------
        teamd   false     teamsyncd_timer  120               NULL
        system  true      NULL             NULL              NULL
    """)
    assert result.output == expected_output
    assert result.exit_code == 0


def test_show_warm_restart_unix_sock_usage_and_namespace(statedb, cfgdb, multi_asic_mock):
    runner = CliRunner()
    arguments = ["-s", "/var/run/redis/redis.sock", "-n", "asic1"]
    result = runner.invoke(
        cli.commands["warm_restart"].commands["config"], arguments,
    )
    expected_output = textwrap.dedent("""\
        Usage: config [OPTIONS]

        Error: Cannot specify both namespace and redis unix socket path
    """)
    assert result.output == expected_output
    assert result.exit_code == 2

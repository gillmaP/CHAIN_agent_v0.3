"""Shared Agent entrypoint contract checks using synthetic inputs."""
import inspect
import unittest
from chain_agents.screening.agent import invoke as screening
from chain_agents.summary.agent import invoke as summary
from chain_agents.tpa.agent import invoke as tpa

class AgentEntrypointTests(unittest.TestCase):
    def test_all_agent_invocations_share_parameter_names(self):
        for invoke in (screening, summary, tpa):
            with self.subTest(invoke=invoke.__module__):
                self.assertEqual(list(inspect.signature(invoke).parameters), ['request', 'snapshot', 'services'])

if __name__ == '__main__':
    unittest.main()

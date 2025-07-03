from typing import List, Dict, Any
import asyncio
import os
import yaml
import platform
from python_on_whales import DockerClient
from mcp.types import TextContent, Tool, Prompt, PromptArgument, GetPromptResult, PromptMessage
from .docker_executor import DockerComposeExecutor

def get_docker_client():
    """Get DockerClient with support for DOCKER_HOST and DOCKER_CONTEXT env vars."""
    docker_host = os.getenv('DOCKER_HOST')
    docker_context = os.getenv('DOCKER_CONTEXT')
    
    if docker_host:
        return DockerClient(host=docker_host)
    elif docker_context:
        return DockerClient(context_name=docker_context)
    else:
        return DockerClient()

docker_client = get_docker_client()


async def parse_port_mapping(host_key: str, container_port: str | int) -> tuple[str, str] | tuple[str, str, str]:
    if '/' in str(host_key):
        host_port, protocol = host_key.split('/')
        if protocol.lower() == 'udp':
            return (str(host_port), str(container_port), 'udp')
        return (str(host_port), str(container_port))

    if isinstance(container_port, str) and '/' in container_port:
        port, protocol = container_port.split('/')
        if protocol.lower() == 'udp':
            return (str(host_key), port, 'udp')
        return (str(host_key), port)

    return (str(host_key), str(container_port))


class DockerHandlers:
    TIMEOUT_AMOUNT = 200

    @staticmethod
    async def handle_create_container(arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            image = arguments["image"]
            container_name = arguments.get("name")
            ports = arguments.get("ports", {})
            environment = arguments.get("environment", {})

            if not image:
                raise ValueError("Image name cannot be empty")

            port_mappings = []
            for host_key, container_port in ports.items():
                mapping = await parse_port_mapping(host_key, container_port)
                port_mappings.append(mapping)

            async def pull_and_run():
                if not docker_client.image.exists(image):
                    await asyncio.to_thread(docker_client.image.pull, image)

                container = await asyncio.to_thread(
                    docker_client.container.run,
                    image,
                    name=container_name,
                    publish=port_mappings,
                    envs=environment,
                    detach=True
                )
                return container

            container = await asyncio.wait_for(pull_and_run(), timeout=DockerHandlers.TIMEOUT_AMOUNT)
            return [TextContent(type="text", text=f"Created container '{container.name}' (ID: {container.id})")]
        except asyncio.TimeoutError:
            return [TextContent(type="text", text=f"Operation timed out after {DockerHandlers.TIMEOUT_AMOUNT} seconds")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating container: {str(e)} | Arguments: {arguments}")]

    @staticmethod
    async def handle_deploy_compose(arguments: Dict[str, Any]) -> List[TextContent]:
        debug_info = []
        try:
            compose_yaml = arguments.get("compose_yaml")
            project_name = arguments.get("project_name")

            if not compose_yaml or not project_name:
                raise ValueError(
                    "Missing required compose_yaml or project_name")

            yaml_content = DockerHandlers._process_yaml(
                compose_yaml, debug_info)
            compose_path = DockerHandlers._save_compose_file(
                yaml_content, project_name)

            try:
                result = await DockerHandlers._deploy_stack(compose_path, project_name, debug_info)
                return [TextContent(type="text", text=result)]
            finally:
                DockerHandlers._cleanup_files(compose_path)

        except Exception as e:
            debug_output = "\n".join(debug_info)
            return [TextContent(type="text", text=f"Error deploying compose stack: {str(e)}\n\nDebug Information:\n{debug_output}")]

    @staticmethod
    def _process_yaml(compose_yaml: str, debug_info: List[str]) -> dict:
        debug_info.append("=== Original YAML ===")
        debug_info.append(compose_yaml)

        try:
            yaml_content = yaml.safe_load(compose_yaml)
            debug_info.append("\n=== Loaded YAML Structure ===")
            debug_info.append(str(yaml_content))
            return yaml_content
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {str(e)}")

    @staticmethod
    def _save_compose_file(yaml_content: dict, project_name: str) -> str:
        compose_dir = os.path.join(os.getcwd(), "docker_compose_files")
        os.makedirs(compose_dir, exist_ok=True)

        compose_yaml = yaml.safe_dump(
            yaml_content, default_flow_style=False, sort_keys=False)
        compose_path = os.path.join(
            compose_dir, f"{project_name}-docker-compose.yml")

        with open(compose_path, 'w', encoding='utf-8') as f:
            f.write(compose_yaml)
            f.flush()
            if platform.system() != 'Windows':
                os.fsync(f.fileno())

        return compose_path

    @staticmethod
    async def _deploy_stack(compose_path: str, project_name: str, debug_info: List[str]) -> str:
        compose = DockerComposeExecutor(compose_path, project_name)

        for command in [compose.down, compose.up]:
            try:
                code, out, err = await command()
                debug_info.extend([
                    f"\n=== {command.__name__.capitalize()} Command ===",
                    f"Return Code: {code}",
                    f"Stdout: {out}",
                    f"Stderr: {err}"
                ])

                if code != 0 and command == compose.up:
                    raise Exception(f"Deploy failed with code {code}: {err}")
            except Exception as e:
                if command != compose.down:
                    raise e
                debug_info.append(f"Warning during {
                                  command.__name__}: {str(e)}")

        code, out, err = await compose.ps()
        service_info = out if code == 0 else "Unable to list services"

        return (f"Successfully deployed compose stack '{project_name}'\n"
                f"Running services:\n{service_info}\n\n"
                f"Debug Info:\n{chr(10).join(debug_info)}")

    @staticmethod
    def _cleanup_files(compose_path: str) -> None:
        try:
            if os.path.exists(compose_path):
                os.remove(compose_path)
            compose_dir = os.path.dirname(compose_path)
            if os.path.exists(compose_dir) and not os.listdir(compose_dir):
                os.rmdir(compose_dir)
        except Exception as e:
            print(f"Warning during cleanup: {str(e)}")

    @staticmethod
    async def handle_get_logs(arguments: Dict[str, Any]) -> List[TextContent]:
        debug_info = []
        try:
            container_name = arguments.get("container_name")
            if not container_name:
                raise ValueError("Missing required container_name")

            debug_info.append(f"Fetching logs for container '{
                              container_name}'")
            logs = await asyncio.to_thread(docker_client.container.logs, container_name, tail=100)

            return [TextContent(type="text", text=f"Logs for container '{container_name}':\n{logs}\n\nDebug Info:\n{chr(10).join(debug_info)}")]
        except Exception as e:
            debug_output = "\n".join(debug_info)
            return [TextContent(type="text", text=f"Error retrieving logs: {str(e)}\n\nDebug Information:\n{debug_output}")]

    @staticmethod
    async def handle_list_containers(arguments: Dict[str, Any]) -> List[TextContent]:
        debug_info = []
        try:
            debug_info.append("Listing all Docker containers")
            containers = await asyncio.to_thread(docker_client.container.list, all=True)
            container_list = "\n".join(
                [f"{c.id[:12]} - {c.name} - {c.state.status}" for c in containers])

            return [TextContent(type="text", text=f"All Docker Containers:\n{container_list}\n\nDebug Info:\n{chr(10).join(debug_info)}")]
        except Exception as e:
            debug_output = "\n".join(debug_info)
            return [TextContent(type="text", text=f"Error listing containers: {str(e)}\n\nDebug Information:\n{debug_output}")]

    @staticmethod
    async def handle_get_container_info(arguments: Dict[str, Any]) -> List[TextContent]:
        debug_info = []
        try:
            container_name = arguments.get("container_name")
            if not container_name:
                raise ValueError("Missing required container_name")

            debug_info.append(f"Getting detailed info for container '{container_name}'")
            
            # Get full container inspection data
            container = await asyncio.to_thread(docker_client.container.inspect, container_name)
            
            # Format comprehensive container information
            info_lines = [
                f"=== Container Information ===",
                f"Name: {container.name}",
                f"ID: {container.id}",
                f"Status: {container.state.status}",
                f"Image: {container.config.image}",
                f"Created: {container.created}",
                f"Started: {container.state.started_at if hasattr(container.state, 'started_at') else 'N/A'}",
                "",
                f"=== Environment Variables ==="
            ]
            
            # Environment variables
            if container.config.env:
                for env_var in container.config.env:
                    info_lines.append(f"  {env_var}")
            else:
                info_lines.append("  No environment variables set")
            
            info_lines.extend(["", f"=== Port Mappings ==="])
            
            # Port mappings
            if hasattr(container, 'network_settings') and container.network_settings.ports:
                for container_port, host_configs in container.network_settings.ports.items():
                    if host_configs:
                        for host_config in host_configs:
                            info_lines.append(f"  {host_config.get('HostIp', '0.0.0.0')}:{host_config['HostPort']} -> {container_port}")
                    else:
                        info_lines.append(f"  {container_port} (not bound to host)")
            else:
                info_lines.append("  No port mappings")
            
            info_lines.extend(["", f"=== Volume Mounts ==="])
            
            # Volume mounts
            if container.mounts:
                for mount in container.mounts:
                    mount_type = getattr(mount, 'type', 'unknown')
                    source = getattr(mount, 'source', 'N/A')
                    destination = getattr(mount, 'destination', 'N/A')
                    mode = getattr(mount, 'mode', 'N/A')
                    info_lines.append(f"  {mount_type}: {source} -> {destination} ({mode})")
            else:
                info_lines.append("  No volume mounts")
            
            info_lines.extend(["", f"=== Network Settings ==="])
            
            # Network information
            if hasattr(container, 'network_settings'):
                networks = getattr(container.network_settings, 'networks', {})
                if networks:
                    for network_name, network_info in networks.items():
                        ip_address = getattr(network_info, 'ip_address', 'N/A')
                        info_lines.append(f"  Network: {network_name} (IP: {ip_address})")
                else:
                    info_lines.append("  No network information available")
            
            info_lines.extend(["", f"=== Resource Limits ==="])
            
            # Resource limits
            if hasattr(container.host_config, 'memory') and container.host_config.memory:
                memory_limit = container.host_config.memory / (1024*1024)  # Convert to MB
                info_lines.append(f"  Memory Limit: {memory_limit:.0f}MB")
            else:
                info_lines.append("  Memory Limit: Not set")
                
            if hasattr(container.host_config, 'cpu_shares') and container.host_config.cpu_shares:
                info_lines.append(f"  CPU Shares: {container.host_config.cpu_shares}")
            else:
                info_lines.append("  CPU Shares: Not set")
            
            info_lines.extend(["", f"=== Working Directory & Command ==="])
            info_lines.append(f"  Working Dir: {getattr(container.config, 'working_dir', 'N/A')}")
            
            if hasattr(container.config, 'cmd') and container.config.cmd:
                cmd_str = ' '.join(container.config.cmd) if isinstance(container.config.cmd, list) else str(container.config.cmd)
                info_lines.append(f"  Command: {cmd_str}")
            else:
                info_lines.append("  Command: N/A")
            
            container_info = "\n".join(info_lines)
            return [TextContent(type="text", text=f"{container_info}\n\nDebug Info:\n{chr(10).join(debug_info)}")]
            
        except Exception as e:
            debug_output = "\n".join(debug_info)
            return [TextContent(type="text", text=f"Error getting container info: {str(e)}\n\nDebug Information:\n{debug_output}")]

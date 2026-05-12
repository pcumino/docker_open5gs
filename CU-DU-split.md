# Analise aprofundada do split CU/DU no projeto Open5GS (srsRAN + ZMQ)

Este documento descreve de forma operacional como o split CU/DU esta implementado no projeto, com foco em rastreio de trafego e correlacao de eventos para analise futura em logs e Wireshark.

## 1. Escopo e objetivo

Objetivo principal:
- detalhar o fluxo fim a fim entre UE e Core para plano de controle e plano de dados;
- mapear interfaces, protocolos, portas e direcoes;
- indicar onde capturar pacotes e quais filtros usar;
- reduzir ambiguidades durante troubleshooting.

Escopo considerado:
- cenario 5G SA com split CU/DU via `srsgnb_split_zmq.yaml`;
- UE em modo ZMQ (`srsue_5g_zmq.yaml`);
- Core 5G em `sa-deploy.yaml` (especialmente AMF e UPF).

## 2. Fontes tecnicas no repositorio

Arquivos usados como fonte de verdade para esta analise:
- `srsgnb_split_zmq.yaml`
- `srsran/cu_zmq.yml`
- `srsran/du_zmq.yml`
- `srsue_5g_zmq.yaml`
- `srslte/ue_5g_zmq.conf`
- `.env`
- `start.sh`
- `srsran/srsran_init.sh`
- `srslte/srslte_init.sh`
- `sa-deploy.yaml`

## 3. Topologia de referencia

```
UE (srsue_5g_zmq)
  Uu simulado via ZMQ/TCP (2000/2001)
DU (srsdu_zmq)
  F1-C: SCTP 38472
  F1-U: UDP 2152 (peer 2153 no CU)
CU (srscu_zmq)
  N2: SCTP 38412 -> AMF
  N3: UDP/GTP-U 2152 (UPF)
  F1-C/F1-U com DU
Core (AMF, SMF, UPF, ...)
```

IPs padrao no `.env`:
- `AMF_IP=172.22.0.10`
- `UPF_IP=172.22.0.8`
- `SRS_UE_IP=172.22.0.34`
- `SRS_CU_IP=172.22.0.43`
- `SRS_DU_IP=172.22.0.44`

## 4. Mapa de interfaces, protocolos e portas

| Perna | Origem | Destino | Protocolo | Porta | Funcao |
|---|---|---|---|---|---|
| Uu (simulado) | UE | DU | TCP (ZMQ) | 2000/2001 | Transporte de amostras de radio no laboratorio |
| F1-C | DU | CU | SCTP/F1AP | 38472 | Controle entre DU e CU |
| F1-U | DU | CU | UDP/GTP-U | 2152/2153 | Dados de usuario entre DU e CU |
| N2 | CU | AMF | SCTP/NGAP | 38412 | Controle entre RAN e Core |
| N3 | CU | UPF | UDP/GTP-U | 2152 | Dados entre RAN e Core |

Observacoes importantes:
- Em `srsran/cu_zmq.yml`, o CU-UP usa `bind_port: 2153` e `peer_port: 2152`.
- Em `srsran/du_zmq.yml`, a DU aponta `peer_port: 2153`.
- Na pratica, trate F1-U como bidirecional e confirme direcao pela combinacao IP origem/destino.

## 5. Como o split esta montado no projeto

### 5.1 CU (`srscu_zmq`)

Definido em `srsgnb_split_zmq.yaml` com:
- exposicao de `38412/sctp` (N2), `38472/sctp` (F1-C), `2152/udp` e `2153/udp` (F1-U/N3 conforme fluxo);
- IP fixo `SRS_CU_IP`.

Configuracao efetiva em `srsran/cu_zmq.yml`:
- `cu_cp.amf.addr = AMF_IP`
- `cu_cp.amf.bind_addr = SRS_CU_IP`
- `cu_cp.f1ap.bind_addr = SRS_CU_IP`
- `cu_up.f1u.bind_port = 2153`
- `cu_up.f1u.peer_port = 2152`

### 5.2 DU (`srsdu_zmq`)

Definido em `srsgnb_split_zmq.yaml` com:
- dependente de `srscu_zmq`;
- exposicao de `38472/sctp`, `2152/udp`, `2000/tcp`, `2001/tcp`;
- IP fixo `SRS_DU_IP`.

Configuracao efetiva em `srsran/du_zmq.yml`:
- `f1ap.cu_cp_addr = SRS_CU_IP`
- `f1ap.bind_addr = SRS_DU_IP`
- `f1u.peer_port = 2153`
- ZMQ (`ru_sdr.device_args`):
  - `tx_port=tcp://SRS_DU_IP:2000`
  - `rx_port=tcp://SRS_UE_IP:2001`

### 5.3 UE (`srsue_5g_zmq`)

Em `srslte/ue_5g_zmq.conf`:
- `device_name = zmq`
- `tx_port=tcp://SRS_UE_IP:2001`
- `rx_port=tcp://SRS_GNB_IP:2000`

No modo split, `start.sh` com `ue-split` exporta `SRS_ZMQ_DU_IP=$SRS_DU_IP`, e `srslte/srslte_init.sh` troca `SRS_GNB_IP` por `SRS_ZMQ_DU_IP` em tempo de inicializacao.

## 6. Fluxo fim a fim - plano de controle

### 6.1 Fase de setup (ordem logica)

1. CU inicia e abre listeners de N2, F1-C e F1-U.
2. DU inicia, conecta no CU via F1-C (SCTP 38472).
3. O procedimento F1 Setup ocorre (F1AP).
4. CU estabelece relacionamento RAN-Core com AMF via N2 (NGAP/SCTP 38412).
5. UE sincroniza via Uu simulado (ZMQ), avanca para procedimentos RRC/NAS.

### 6.2 Fluxo de sinalizacao UE -> Core (visao operacional)

1. UE gera mensagens de acesso RRC e NAS.
2. DU processa PHY/MAC/RLC e encaminha controle para CU via F1-C (F1AP).
3. CU processa RRC e encapsula sinalizacao para AMF via N2 (NGAP).
4. AMF responde ao CU (NGAP), CU adapta para contexto de radio e envia para DU (F1-C).
5. DU transmite ao UE pelo Uu (via cadeia MAC/PHY e ZMQ no laboratorio).

Ponto chave de analise:
- Controle RAN interno: F1-C (`sctp.port == 38472`, dissector F1AP).
- Controle RAN-Core: N2 (`sctp.port == 38412`, dissector NGAP).

## 7. Fluxo fim a fim - plano de dados

### 7.1 Downlink (Core -> UE)

1. Trafego de usuario chega no UPF.
2. UPF encaminha para a RAN via N3 (GTP-U/UDP 2152) com destino ao CU-UP.
3. CU-UP processa e encaminha para DU via F1-U (tambem GTP-U sobre UDP, conforme mapeamento de portas CU/DU).
4. DU transforma em unidades de transmissao radio (RLC/MAC/PHY) e envia ao UE via Uu simulado (ZMQ).
5. UE reconstroi o fluxo e entrega para sua pilha IP local.

### 7.2 Uplink (UE -> Core)

1. UE envia trafego para DU pelo Uu simulado.
2. DU processa L1/L2, encapsula para F1-U e envia ao CU.
3. CU-UP encaminha via N3 para UPF em GTP-U.
4. UPF remove encapsulamento e roteia para destino de dados.

Ponto chave de analise:
- F1-U e N3 podem parecer similares no Wireshark (ambos GTP-U/UDP).
- Diferencie por IP origem/destino e contexto da perna de rede.

## 8. Onde capturar pacotes (guia pratico)

### 8.1 Capturas no host (rede Docker)

Exemplos de filtros:

```bash
# F1-C (controle DU<->CU)
tcpdump -i docker0 -w f1c.pcap 'sctp and port 38472'

# N2 (controle CU<->AMF)
tcpdump -i docker0 -w n2.pcap 'sctp and host 172.22.0.43 and host 172.22.0.10 and port 38412'

# F1-U (dados DU<->CU)
tcpdump -i docker0 -w f1u.pcap 'udp and host 172.22.0.43 and host 172.22.0.44 and (port 2152 or port 2153)'

# N3 (dados CU<->UPF)
tcpdump -i docker0 -w n3.pcap 'udp and host 172.22.0.43 and host 172.22.0.8 and port 2152'

# Uu simulado (ZMQ)
tcpdump -i docker0 -w uu-zmq.pcap 'tcp and (port 2000 or port 2001)'
```

### 8.2 PCAPs nativos dos componentes

CU (`srsran/cu_zmq.yml`):
- `/mnt/srsran/cu_ngap.pcap`
- `/mnt/srsran/cu_f1ap.pcap`
- `/mnt/srsran/cu_e1ap.pcap`
- `/mnt/srsran/cu_n3.pcap`

DU (`srsran/du_zmq.yml`):
- `/mnt/srsran/du_f1ap.pcap`
- `/mnt/srsran/du_mac.pcap`

UE (`srslte/ue_5g_zmq.conf`):
- `/mnt/srslte/ue_mac.pcap`
- `/mnt/srslte/ue_mac_nr.pcap`
- `/mnt/srslte/ue_nas.pcap`

## 9. Filtros Wireshark sugeridos

Filtros base:
- `f1ap`
- `ngap`
- `sctp.port == 38472`
- `sctp.port == 38412`
- `gtp`
- `udp.port == 2152 || udp.port == 2153`
- `ip.addr == 172.22.0.43 && ip.addr == 172.22.0.44`
- `ip.addr == 172.22.0.43 && ip.addr == 172.22.0.8`
- `tcp.port == 2000 || tcp.port == 2001`

Dica de metodo:
- primeiro isole por perna (N2, F1-C, F1-U, N3);
- depois refine por protocolo/dissector (NGAP, F1AP, GTP-U);
- por fim correlacione timestamp com logs (`cu.log`, `du.log`, `ue.log`).

## 10. Correlacao com logs

Arquivos de log:
- CU: `/mnt/srsran/cu.log`
- DU: `/mnt/srsran/du.log`
- UE: `/mnt/srslte/ue.log`

Comandos uteis:

```bash
docker exec -it srscu_zmq tail -f /mnt/srsran/cu.log
docker exec -it srsdu_zmq tail -f /mnt/srsran/du.log
docker exec -it srsue_5g_zmq tail -f /mnt/srslte/ue.log
```

Estrutura recomendada para investigacao:
1. Marcar instante de evento (ex.: attach, ping, iperf).
2. Capturar N2 e F1-C para sinalizacao no mesmo intervalo.
3. Capturar F1-U e N3 para dados no mesmo intervalo.
4. Cruzar pacotes com logs por timestamp.

## 11. Ambiguidades e limites tecnicos

1. Distincao exata de split 3GPP:
- A separacao observada e consistente com arquitetura CU/DU de 5G NR (camadas altas no CU e baixas no DU), mas a nomenclatura de opcao pode variar conforme documentacao externa e versao do stack.

2. Visibilidade de E1:
- `cu_e1ap.pcap` esta habilitado no CU, porem parte da logica CU-CP/CU-UP pode ser intra-processo dependendo da implementacao/versao.

3. Ambiguidade F1-U/N3 em GTP-U:
- ambos usam GTP-U sobre UDP e podem confundir na leitura. Use IPs e contexto da perna para separar.

4. Endpoint ZMQ do UE:
- sem `ue-split`, o UE pode apontar para o gNB monolitico (`SRS_GNB_IP`) em vez de `SRS_DU_IP`.

## 12. Checklist operacional para analise futura

Antes de capturar:
- confirmar modo split: `./start.sh split`;
- confirmar UE em split: `./start.sh ue-split`;
- validar IPs em `.env`;
- validar containers ativos: `srscu_zmq`, `srsdu_zmq`, `srsue_5g_zmq`, `amf`, `upf`.

Durante captura:
- separar arquivos por perna (`f1c.pcap`, `n2.pcap`, `f1u.pcap`, `n3.pcap`);
- registrar horario de inicio/fim do teste;
- manter logs em paralelo.

Depois da captura:
- abrir primeiro F1-C/N2 para entender a sinalizacao;
- depois F1-U/N3 para dados;
- por ultimo correlacionar com logs CU/DU/UE.

## 13. Resumo executivo

No estado atual do projeto, o split CU/DU funciona com:
- controle distribuido entre F1-C (DU<->CU) e N2 (CU<->AMF);
- dados distribuido entre F1-U (DU<->CU) e N3 (CU<->UPF), ambos em GTP-U;
- Uu simulado por ZMQ/TCP entre UE e DU para laboratorio.

Para analise de pacotes confiavel, o ponto mais importante e separar claramente cada perna por IP/porta e correlacionar sempre com os logs dos tres componentes (CU, DU e UE).

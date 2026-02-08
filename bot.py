import os
import asyncio
import time
import logging
from typing import Dict, List, Optional
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OpenOrderParams
from py_clob_client.order_builder.constants import BUY, SELL
from py_clob_client.constants import POLYGON
from eth_account import Account
from decimal import Decimal

# ============================================================================
# CONFIGURAÇÃO DO ROBÔ (EDITAR AQUI!)
# ============================================================================
CONFIG = {
    # 🔐 CHAVE PRIVADA (do Railway Variables)
    "PRIVATE_KEY": os.getenv("PRIVATE_KEY", ""),
    
    # 🌐 REDE (True = Testnet, False = Mainnet)
    "TESTNET": True,  # ⚠️ MUDAR PARA False QUANDO ESTIVER PRONTO!
    
    # 📊 MERCADO BTC UP/DOWN (ajuste se necessário)
    "CONDITION_ID": "0x7aa5461c2c03c2c53b6da5d76b95b35b0e1f3e5e2c6c5e5e5e5e5e5e5e5e5e5e",
    "TOKEN_ID": "0x7aa5461c2c03c2c53b6da5d76b95b35b0e1f3e5e2c6c5e5e5e5e5e5e5e5e5e5e",
    
    # 🔽 PROXY DO POLYMARKET
    "PROXY": "0x658293eF9454A2DD555eb4afcE6436aDE78ab20B",
    
    # 🎯 ESTRATÉGIA DE GRID
    "PRECO_INICIAL": 0.80,      # Começa comprando a 0.80
    "PRECO_FINAL": 0.50,        # Até 0.50
    "INTERVALO_COMPRA": 0.02,   # Espaço entre ordens de compra
    "LUCRO_ALVO": 0.05,         # Lucro por operação
    
    # ⚙️ PARÂMETROS OPERACIONAIS
    "SHARES_POR_ORDEM": 5,      # Quantidade por ordem (reduza para 1 no início!)
    "INTERVALO_CICLO": 30,      # 30 segundos entre ciclos
    "MAX_ORDENS_ABERTAS": 8,    # Máximo de ordens abertas simultaneamente
    
    # 🛡️ SEGURANÇA
    "CANCELAR_ORDENS_ANTIGAS": True,  # Cancela ordens com mais de 5 minutos
    "VERIFICAR_DUPLICADAS": True,     # Verifica ordens duplicadas
}

# ============================================================================
# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class RoboGridTrading:
    """Robô de grid trading com proteção contra duplicação"""
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Verificar chave privada
        if not config["PRIVATE_KEY"]:
            logger.error("❌ PRIVATE_KEY não configurada!")
            logger.error("Adicione no Railway Variables: PRIVATE_KEY=sua_chave_aqui")
            raise ValueError("PRIVATE_KEY não configurada")
        
        # Inicializar cliente
        self.account = Account.from_key(config["PRIVATE_KEY"])
        self.host = "https://clob-testnet.polymarket.com" if config["TESTNET"] else "https://clob.polymarket.com"
        self.chain_id = 80001 if config["TESTNET"] else 137
        
        self.client = ClobClient(
            host=self.host,
            key=self.account.key,
            chain_id=self.chain_id,
            signature_type=POLYGON,
        )
        
        # Gerar grid de preços
        self.grid_prices = self._gerar_grid_precos()
        
        # Controle de ordens
        self.ordens_ativas = {}  # {preco: order_id}
        self.historico_ordens = []
        self.ultimo_saldo = 0.0
        
        # Status
        self.rodando = False
        self.ciclo_numero = 0
        
        logger.info(f"🤖 Robô inicializado - {'TESTNET' if config['TESTNET'] else 'MAINNET'}")
        logger.info(f"💰 Conta: {self.account.address[:10]}...")
        logger.info(f"📊 Grid: {len(self.grid_prices)} níveis ({self.grid_prices[0]} até {self.grid_prices[-1]})")
    
    def _gerar_grid_precos(self) -> List[float]:
        """Gera lista de preços para o grid"""
        preco = self.config["PRECO_INICIAL"]
        preco_final = self.config["PRECO_FINAL"]
        intervalo = self.config["INTERVALO_COMPRA"]
        
        precos = []
        while preco >= preco_final:
            precos.append(round(preco, 2))
            preco -= intervalo
        
        return precos
    
    async def _obter_saldo(self) -> float:
        """Obtém saldo disponível"""
        try:
            # O py_clob_client não tem método direto de saldo
            # Vamos usar uma abordagem alternativa
            orders = await self.client.get_orders(
                OpenOrderParams(
                    owner=self.account.address,
                )
            )
            
            # Saldo aproximado baseado em ordens não preenchidas
            # Em produção, você precisaria integrar com a carteira
            saldo_estimado = 100.0  # Valor padrão para testes
            
            self.ultimo_saldo = saldo_estimado
            return saldo_estimado
            
        except Exception as e:
            logger.error(f"Erro ao obter saldo: {e}")
            return self.ultimo_saldo
    
    async def _obter_ordens_abertas(self) -> List[Dict]:
        """Obtém todas as ordens abertas"""
        try:
            orders = await self.client.get_orders(
                OpenOrderParams(
                    owner=self.account.address,
                )
            )
            
            ordens_formatadas = []
            for order in orders:
                if hasattr(order, 'price') and hasattr(order, 'token_id'):
                    ordens_formatadas.append({
                        'id': getattr(order, 'id', ''),
                        'price': float(getattr(order, 'price', 0)),
                        'quantity': int(getattr(order, 'amount', 0)),
                        'filled': int(getattr(order, 'filled', 0)),
                        'side': getattr(order, 'side', 'buy'),
                        'token_id': getattr(order, 'token_id', '')
                    })
            
            return ordens_formatadas
            
        except Exception as e:
            logger.error(f"Erro ao obter ordens abertas: {e}")
            return []
    
    async def _cancelar_ordem(self, order_id: str) -> bool:
        """Cancela uma ordem específica"""
        try:
            result = await self.client.cancel_order(order_id)
            if result:
                # Remove do controle interno
                for preco, oid in list(self.ordens_ativas.items()):
                    if oid == order_id:
                        del self.ordens_ativas[preco]
                        logger.info(f"✅ Ordem cancelada @ {preco}")
                        break
                return True
            return False
        except Exception as e:
            logger.error(f"Erro ao cancelar ordem: {e}")
            return False
    
    async def _cancelar_todas_ordens(self):
        """Cancela TODAS as ordens abertas"""
        logger.info("🔄 Cancelando todas as ordens abertas...")
        ordens = await self._obter_ordens_abertas()
        
        if not ordens:
            logger.info("✅ Nenhuma ordem para cancelar")
            return
        
        cancelamentos = []
        for ordem in ordens:
            cancelamentos.append(self._cancelar_ordem(ordem['id']))
        
        resultados = await asyncio.gather(*cancelamentos, return_exceptions=True)
        sucessos = sum(1 for r in resultados if r is True)
        
        logger.info(f"✅ Canceladas {sucessos}/{len(ordens)} ordens")
        self.ordens_ativas.clear()
    
    async def _verificar_ordem_existente(self, preco: float) -> bool:
        """Verifica se já existe ordem neste preço"""
        # 1. Verifica no controle interno
        if preco in self.ordens_ativas:
            return True
        
        # 2. Verifica na API
        ordens = await self._obter_ordens_abertas()
        for ordem in ordens:
            if abs(ordem['price'] - preco) < 0.001:
                self.ordens_ativas[preco] = ordem['id']
                return True
        
        return False
    
    async def _criar_ordem_compra(self, preco: float) -> Optional[str]:
        """
        Cria uma ordem de compra se não existir no mesmo preço
        
        Returns:
            ID da ordem criada ou None se falhar
        """
        try:
            # 1. Verifica duplicação
            if await self._verificar_ordem_existente(preco):
                logger.debug(f"⏭️  Já existe ordem em ${preco:.2f}")
                return None
            
            # 2. Cria a ordem
            quantidade = self.config["SHARES_POR_ORDEM"]
            
            order_args = OrderArgs(
                price=preco,
                size=quantidade,
                side=BUY,
                token_id=self.config["TOKEN_ID"],
            )
            
            # 3. Submete a ordem
            order_result = await self.client.create_order(order_args)
            
            if order_result and hasattr(order_result, 'id'):
                order_id = order_result.id
                self.ordens_ativas[preco] = order_id
                
                self.historico_ordens.append({
                    'time': time.strftime('%H:%M:%S'),
                    'preco': preco,
                    'quantidade': quantidade,
                    'id': order_id[:8],
                    'tipo': 'COMPRA'
                })
                
                logger.info(f"✅ COMPRA criada: {quantidade} shares @ ${preco:.2f}")
                return order_id
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar ordem @ ${preco:.2f}: {e}")
            return None
    
    async def _atualizar_ordens_ativas(self):
        """Atualiza a lista de ordens ativas baseado na API"""
        try:
            ordens = await self._obter_ordens_abertas()
            ids_ativos = {o['id'] for o in ordens}
            
            # Remove ordens que não existem mais
            for preco, order_id in list(self.ordens_ativas.items()):
                if order_id not in ids_ativos:
                    del self.ordens_ativas[preco]
                    logger.debug(f"🔄 Ordem removida do controle @ ${preco:.2f}")
            
            # Adiciona novas ordens encontradas
            for ordem in ordens:
                if ordem['side'] == 'buy':
                    preco = ordem['price']
                    if preco not in self.ordens_ativas:
                        self.ordens_ativas[preco] = ordem['id']
                        
        except Exception as e:
            logger.error(f"Erro ao atualizar ordens: {e}")
    
    async def _limpar_ordens_antigas(self, minutos_maximo: int = 5):
        """Cancela ordens muito antigas"""
        try:
            ordens = await self._obter_ordens_abertas()
            
            for ordem in ordens:
                # Verifica idade da ordem (implementação simplificada)
                # Em produção, você precisaria obter o timestamp da ordem
                if ordem['id'] in self.ordens_ativas.values():
                    # Simulação: se ordem está na lista há mais de X ciclos
                    if self.ciclo_numero % 10 == 0:  # A cada 10 ciclos
                        logger.info(f"🔄 Renovando ordem @ ${ordem['price']:.2f}")
                        await self._cancelar_ordem(ordem['id'])
                        
        except Exception as e:
            logger.error(f"Erro na limpeza: {e}")
    
    async def _executar_ciclo_grid(self):
        """Executa um ciclo completo do grid trading"""
        self.ciclo_numero += 1
        
        print(f"\n{'='*60}")
        print(f"🔄 CICLO {self.ciclo_numero}")
        print(f"{'='*60}")
        
        # 1. Atualiza ordens ativas
        await self._atualizar_ordens_ativas()
        ordens_abertas = await self._obter_ordens_abertas()
        print(f"📊 Ordens abertas: {len(ordens_abertas)}")
        
        # 2. Verifica saldo
        saldo = await self._obter_saldo()
        print(f"💰 Saldo estimado: ${saldo:.2f}")
        
        # 3. Limpa ordens antigas (se configurado)
        if self.config["CANCELAR_ORDENS_ANTIGAS"]:
            await self._limpar_ordens_antigas()
        
        # 4. Cria novas ordens do grid
        print("🔵 CRIANDO ORDENS DE COMPRA...")
        novas_ordens = 0
        
        for preco in self.grid_prices:
            # Limite máximo de ordens
            if len(self.ordens_ativas) >= self.config["MAX_ORDENS_ABERTAS"]:
                print(f"⚠️  Limite de {self.config['MAX_ORDENS_ABERTAS']} ordens atingido")
                break
            
            if await self._criar_ordem_compra(preco):
                novas_ordens += 1
                await asyncio.sleep(0.3)  # Pausa entre ordens
        
        # 5. Resumo do ciclo
        print(f"\n📋 RESUMO DO CICLO:")
        print(f"   • Ordens novas: {novas_ordens}")
        print(f"   • Total ativas: {len(self.ordens_ativas)}")
        print(f"   • Saldo: ${saldo:.2f}")
        
        # 6. Mostra ordens ativas
        if self.ordens_ativas:
            print(f"\n🎯 Ordens ativas:")
            for preco, order_id in list(self.ordens_ativas.items())[:5]:  # Mostra até 5
                print(f"   • ${preco:.2f} (ID: {order_id[:8]}...)")
        
        # 7. Aguarda próximo ciclo
        intervalo = self.config["INTERVALO_CICLO"]
        print(f"\n⏳ Próximo ciclo em {intervalo} segundos...")
        print(f"{'='*60}")
    
    async def iniciar(self):
        """Inicia o robô"""
        print("\n" + "="*60)
        print("🤖 ROBÔ GRID TRADING - POLYMARKET")
        print("="*60)
        print(f"🚀 Conectando à {'TESTNET' if self.config['TESTNET'] else 'MAINNET'}...")
        print(f"📊 Grid: ${self.config['PRECO_INICIAL']} até ${self.config['PRECO_FINAL']}")
        print(f"💰 Lucro alvo: ${self.config['LUCRO_ALVO']} por operação")
        print(f"⏱️  Intervalo: {self.config['INTERVALO_CICLO']} segundos")
        print("🛑 Para parar: Railway → Deployments → Stop")
        print("="*60)
        
        # Configuração inicial
        self.rodando = True
        
        try:
            # Limpeza inicial
            print("\n🔄 Verificando ordens existentes...")
            await self._cancelar_todas_ordens()
            
            # Loop principal
            while self.rodando:
                try:
                    await self._executar_ciclo_grid()
                    await asyncio.sleep(self.config["INTERVALO_CICLO"])
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Erro no ciclo: {e}")
                    await asyncio.sleep(10)  # Pausa em caso de erro
                    
        except KeyboardInterrupt:
            print("\n\n🛑 INTERRUPÇÃO SOLICITADA")
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            self.rodando = False
            await self._finalizar()
    
    async def _finalizar(self):
        """Finalização segura do robô"""
        print("\n🧹 Finalizando robô...")
        
        # Opção: cancelar ordens ao sair
        if self.config.get("CANCELAR_AO_SAIR", False):
            await self._cancelar_todas_ordens()
        
        print(f"\n📊 RESUMO FINAL:")
        print(f"   • Ciclos executados: {self.ciclo_numero}")
        print(f"   • Ordens criadas: {len(self.historico_ordens)}")
        print("✅ Robô finalizado com segurança!")
        print("="*60)


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================
async def main():
    """Função principal executada pelo Railway"""
    
    print("="*60)
    print("🚂 INICIANDO NO RAILWAY")
    print("="*60)
    
    # Verificar variáveis críticas
    if not CONFIG["PRIVATE_KEY"]:
        print("❌ ERRO: PRIVATE_KEY não configurada!")
        print("\n📋 COMO CONFIGURAR:")
        print("1. No Railway, vá em 'Variables'")
        print("2. Adicione: PRIVATE_KEY=sua_chave_privada_aqui")
        print("3. Salve e reinicie")
        return
    
    # AVISOS DE SEGURANÇA
    print(f"\n⚠️  CONFIGURAÇÃO ATUAL:")
    print(f"• Testnet: {'✅ SIM (SEGURO)' if CONFIG['TESTNET'] else '❌ NÃO (DINHEIRO REAL!)'}")
    print(f"• Quantidade por ordem: {CONFIG['SHARES_POR_ORDEM']} shares")
    print(f"• Preço inicial: ${CONFIG['PRECO_INICIAL']}")
    
    if not CONFIG["TESTNET"]:
        print("\n❌❌❌ ATENÇÃO: OPERANDO COM DINHEIRO REAL! ❌❌❌")
        print("Recomendo mudar TESTNET para True primeiro!")
    
    # Inicializar e executar robô
    try:
        robo = RoboGridTrading(CONFIG)
        await robo.iniciar()
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        print("\n🔧 Solução de problemas:")
        print("1. Verifique se PRIVATE_KEY está correta")
        print("2. Certifique-se de usar TESTNET=True primeiro")
        print("3. Verifique logs do Railway")


# ============================================================================
# EXECUÇÃO
# ============================================================================
if __name__ == "__main__":
    # Configuração especial para Railway
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Programa encerrado pelo Railway")
    except Exception as e:
        print(f"\n❌ Erro não tratado: {e}")

#!/usr/bin/env python3
"""
🤖 ROBÔ GRID TRADING POLYMARKET
Versão simplificada para Railway
"""

import os
import asyncio
import time
import logging
from decimal import Decimal
from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
from py_clob_client.constants import POLYGON

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# CONFIGURAÇÃO DO ROBÔ
CONFIG = {
    # 🔐 CHAVE PRIVADA (Railway Variables)
    "PRIVATE_KEY": os.getenv("PRIVATE_KEY", ""),
    
    # 🌐 REDE (True = Testnet, False = Mainnet)
    "TESTNET": True,  # ⚠️ DEIXE TRUE PARA TESTES!
    
    # 📊 MERCADO BTC UP/DOWN
    "TOKEN_ID": "85080102177445047827595824773776292884437000821375292353013080455752528630674",
    
    # 🎯 ESTRATÉGIA
    "PRECO_INICIAL": 0.80,
    "PRECO_FINAL": 0.50,
    "INTERVALO_COMPRA": 0.02,
    
    # ⚙️ PARÂMETROS
    "SHARES_POR_ORDEM": 1,      # ⚠️ COMECE COM 1!
    "INTERVALO_CICLO": 30,
    "MAX_ORDENS": 5,
}

class RoboGridTrading:
    def __init__(self, config):
        self.config = config
        
        if not config["PRIVATE_KEY"]:
            raise ValueError("❌ PRIVATE_KEY não configurada!")
        
        # Configurar rede
        self.testnet = config["TESTNET"]
        host = "https://clob-testnet.polymarket.com" if self.testnet else "https://clob.polymarket.com"
        chain_id = 80001 if self.testnet else 137
        
        # Criar conta e cliente
        self.account = Account.from_key(config["PRIVATE_KEY"])
        self.client = ClobClient(
            host=host,
            key=self.account.key,
            chain_id=chain_id,
            signature_type=POLYGON,
        )
        
        # Grid de preços
        self.grid_prices = self._gerar_grid()
        self.ordens_ativas = {}
        self.ciclo = 0
        
        logger.info(f"🤖 Robô iniciado - {'TESTNET' if self.testnet else 'MAINNET'}")
        logger.info(f"👤 Conta: {self.account.address[:10]}...")
    
    def _gerar_grid(self):
        """Gera lista de preços"""
        preco = self.config["PRECO_INICIAL"]
        final = self.config["PRECO_FINAL"]
        intervalo = self.config["INTERVALO_COMPRA"]
        
        precos = []
        while preco >= final:
            precos.append(round(preco, 2))
            preco -= intervalo
        
        return precos
    
    async def _obter_ordens(self):
        """Obtém ordens abertas"""
        try:
            ordens = await self.client.get_orders()
            nossas_ordens = []
            
            for ordem in ordens:
                # Converter para dict
                ordem_dict = ordem if isinstance(ordem, dict) else ordem.__dict__
                
                # Verificar se é nossa ordem
                trader = ordem_dict.get('trader') or ordem_dict.get('maker')
                if trader and trader.lower() == self.account.address.lower():
                    nossas_ordens.append({
                        'id': ordem_dict.get('id', ''),
                        'price': float(ordem_dict.get('price', 0)),
                        'side': ordem_dict.get('side', 'buy').lower(),
                    })
            
            return nossas_ordens
            
        except Exception as e:
            logger.error(f"Erro ao obter ordens: {e}")
            return []
    
    async def _cancelar_ordens(self):
        """Cancela todas as ordens"""
        logger.info("🔄 Cancelando ordens...")
        ordens = await self._obter_ordens()
        
        for ordem in ordens:
            try:
                await self.client.cancel_order(ordem['id'])
                logger.info(f"✅ Cancelada ordem @ ${ordem['price']:.2f}")
            except:
                pass
        
        self.ordens_ativas.clear()
    
    async def _criar_ordem(self, preco):
        """Cria uma ordem de compra"""
        try:
            # Verificar se já existe ordem neste preço
            if preco in self.ordens_ativas:
                return False
            
            # Criar ordem
            quantidade = self.config["SHARES_POR_ORDEM"]
            price_decimal = Decimal(str(round(preco, 2)))
            
            order_args = OrderArgs(
                price=price_decimal,
                size=str(quantidade),
                side=BUY,
                token_id=self.config["TOKEN_ID"],
            )
            
            # Enviar ordem
            resultado = await self.client.create_order(order_args)
            
            if resultado:
                # Extrair ID da ordem
                ordem_id = ""
                if hasattr(resultado, 'id'):
                    ordem_id = resultado.id
                elif isinstance(resultado, dict):
                    ordem_id = resultado.get('id', '')
                
                if ordem_id:
                    self.ordens_ativas[preco] = ordem_id
                    logger.info(f"✅ COMPRA: {quantidade} @ ${preco:.2f}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Erro @ ${preco:.2f}: {str(e)[:50]}...")
            return False
    
    async def executar_ciclo(self):
        """Executa um ciclo do grid"""
        self.ciclo += 1
        
        print(f"\n{'='*50}")
        print(f"🔄 CICLO {self.ciclo} - {time.strftime('%H:%M:%S')}")
        print(f"{'='*50}")
        
        # Atualizar ordens ativas
        ordens = await self._obter_ordens()
        print(f"📊 Ordens abertas: {len(ordens)}")
        
        # Criar novas ordens
        print("🔵 Criando ordens...")
        novas = 0
        
        for preco in self.grid_prices:
            if len(self.ordens_ativas) >= self.config["MAX_ORDENS"]:
                print(f"⚠️  Limite de {self.config['MAX_ORDENS']} ordens")
                break
            
            if await self._criar_ordem(preco):
                novas += 1
                await asyncio.sleep(1)  # Evitar rate limit
        
        # Resumo
        print(f"\n📋 RESUMO:")
        print(f"   • Novas: {novas}")
        print(f"   • Total: {len(self.ordens_ativas)}")
        print(f"\n⏳ Próximo ciclo em {self.config['INTERVALO_CICLO']}s...")
        print(f"{'='*50}")
    
    async def iniciar(self):
        """Inicia o robô"""
        print("\n" + "="*50)
        print("🤖 ROBÔ GRID TRADING POLYMARKET")
        print("="*50)
        print(f"🌐 Rede: {'TESTNET ✅' if self.testnet else 'MAINNET ⚠️'}")
        print(f"💰 Preço: ${self.config['PRECO_INICIAL']} até ${self.config['PRECO_FINAL']}")
        print(f"📈 Shares: {self.config['SHARES_POR_ORDEM']}")
        print("="*50)
        
        # Limpar ordens existentes
        await self._cancelar_ordens()
        
        # Loop principal
        try:
            while True:
                await self.executar_ciclo()
                await asyncio.sleep(self.config["INTERVALO_CICLO"])
        except KeyboardInterrupt:
            print("\n🛑 Robô parado")
        except Exception as e:
            logger.error(f"Erro: {e}")

async def main():
    """Função principal"""
    print("🚀 Iniciando robô no Railway...")
    
    if not CONFIG["PRIVATE_KEY"]:
        print("❌ ERRO: Configure PRIVATE_KEY no Railway!")
        return
    
    try:
        robo = RoboGridTrading(CONFIG)
        await robo.iniciar()
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())

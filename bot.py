#!/usr/bin/env python3
"""
🤖 ROBÔ GRID TRADING - VERSÃO SIMPLIFICADA
Usa apenas Private Key (sem API Credentials)
"""

import os
import asyncio
import time
import logging
from web3 import Web3
from eth_account import Account
import json

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# CONFIGURAÇÃO DO ROBÔ
CONFIG = {
    # 🔐 CHAVE PRIVADA (Railway Variables)
    "PRIVATE_KEY": os.getenv("PRIVATE_KEY", ""),
    
    # 🌐 REDE
    "RPC_URL": "https://polygon-mumbai.infura.io/v3/",  # Testnet
    # "RPC_URL": "https://polygon-mainnet.infura.io/v3/",  # Mainnet
    
    # 📊 MERCADO BTC UP/DOWN
    "MARKET_ADDRESS": "0xb6eada42c7b956fc2ecc5d28e2b35c6db0a93b4f",  # Testnet BTC Up/Down
    
    # 🎯 ESTRATÉGIA
    "PRECO_INICIAL": 0.80,
    "PRECO_FINAL": 0.50,
    "INTERVALO_COMPRA": 0.02,
    
    # ⚙️ PARÂMETROS
    "SHARES_POR_ORDEM": 1,  # ⚠️ COMECE COM 1!
    "INTERVALO_CICLO": 30,
    "MAX_ORDENS": 5,
}

class SimplePolyBot:
    """Robô simplificado que interage diretamente com contrato"""
    
    def __init__(self, config):
        self.config = config
        
        if not config["PRIVATE_KEY"]:
            raise ValueError("❌ PRIVATE_KEY não configurada!")
        
        # Configurar Web3
        self.w3 = Web3(Web3.HTTPProvider(config["RPC_URL"]))
        self.account = Account.from_key(config["PRIVATE_KEY"])
        
        # Grid de preços
        self.grid_prices = self._gerar_grid()
        self.ordens_criadas = []
        
        logger.info(f"🤖 Robô iniciado")
        logger.info(f"👤 Conta: {self.account.address}")
        logger.info(f"💰 Saldo: {self.w3.eth.get_balance(self.account.address) / 10**18:.4f} MATIC")
    
    def _gerar_grid(self):
        """Gera lista de preços"""
        preco = self.config["PRECO_INICIAL"]
        final = self.config["PRECO_FINAL"]
        intervalo = self.config["INTERVALO_COMPRA"]
        
        precos = []
        while preco >= final:
            precos.append(round(preco, 2))
            preco -= intervalo
        
        logger.info(f"📊 Grid: {len(precos)} níveis")
        return precos
    
    async def verificar_saldo(self):
        """Verifica saldo em MATIC"""
        try:
            saldo_wei = self.w3.eth.get_balance(self.account.address)
            saldo_matic = saldo_wei / 10**18
            return saldo_matic
        except Exception as e:
            logger.error(f"Erro ao verificar saldo: {e}")
            return 0
    
    async def criar_ordens_simuladas(self):
        """Simula criação de ordens (para teste)"""
        print(f"\n{'='*50}")
        print(f"🔄 CICLO - {time.strftime('%H:%M:%S')}")
        print(f"{'='*50}")
        
        # Verificar saldo
        saldo = await self.verificar_saldo()
        print(f"💰 Saldo: {saldo:.4f} MATIC")
        
        print("🔵 SIMULANDO ordens de compra...")
        
        ordens_novas = 0
        for preco in self.grid_prices[:self.config["MAX_ORDENS"]]:
            if ordens_novas >= self.config["MAX_ORDENS"]:
                break
            
            custo = preco * self.config["SHARES_POR_ORDEM"]
            
            if saldo > custo * 1.1:  # 10% de margem
                timestamp = int(time.time())
                ordem_id = f"order_{timestamp}_{preco}"
                
                self.ordens_criadas.append({
                    'id': ordem_id,
                    'preco': preco,
                    'quantidade': self.config["SHARES_POR_ORDEM"],
                    'custo': custo,
                    'time': time.strftime('%H:%M:%S')
                })
                
                print(f"✅ SIMULAÇÃO: Buy {self.config['SHARES_POR_ORDEM']} @ ${preco:.2f}")
                ordens_novas += 1
                
                # Simular pausa
                await asyncio.sleep(0.5)
            else:
                print(f"⏭️  Saldo insuficiente para ${preco:.2f}")
        
        # Resumo
        print(f"\n📋 RESUMO:")
        print(f"   • Ordens simuladas: {ordens_novas}")
        print(f"   • Total acumulado: {len(self.ordens_criadas)}")
        print(f"   • Saldo atual: {saldo:.4f} MATIC")
        
        # Mostrar últimas ordens
        if self.ordens_criadas[-3:]:
            print(f"\n📝 Últimas ordens:")
            for ordem in self.ordens_criadas[-3:]:
                print(f"   • {ordem['time']} - ${ordem['preco']:.2f}")
        
        print(f"\n⏳ Próximo ciclo em {self.config['INTERVALO_CICLO']}s...")
        print(f"{'='*50}")
    
    async def executar(self):
        """Executa o robô"""
        print("\n" + "="*50)
        print("🤖 SIMULADOR GRID TRADING")
        print("="*50)
        print("⚠️  MODO SIMULAÇÃO ATIVADO")
        print("📊 As ordens são apenas SIMULAÇÕES")
        print("💸 NENHUM dinheiro real está sendo usado")
        print("="*50)
        
        # Verificar conexão
        if not self.w3.is_connected():
            print("❌ ERRO: Não conectado à blockchain!")
            return
        
        print(f"✅ Conectado à rede")
        print(f"👤 Conta: {self.account.address[:10]}...")
        
        ciclo = 0
        try:
            while True:
                ciclo += 1
                print(f"\n📈 CICLO {ciclo}")
                await self.criar_ordens_simuladas()
                await asyncio.sleep(self.config["INTERVALO_CICLO"])
                
        except KeyboardInterrupt:
            print("\n🛑 Robô parado pelo usuário")
        except Exception as e:
            print(f"❌ Erro: {e}")

async def main():
    """Função principal"""
    print("🚀 Iniciando SIMULADOR de Grid Trading...")
    print("="*50)
    
    # Verificar private key
    if not CONFIG["PRIVATE_KEY"]:
        print("❌ ERRO: Configure PRIVATE_KEY no Railway!")
        print("\n📋 Como configurar:")
        print("1. Railway → Variables")
        print("2. Add: PRIVATE_KEY=sua_chave_aqui")
        print("3. Save & Restart")
        return
    
    print(f"✅ Private key configurada")
    print(f"⚠️  MODO: SIMULAÇÃO (sem API Credentials)")
    print("="*50)
    
    try:
        bot = SimplePolyBot(CONFIG)
        await bot.executar()
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    # Adicionar estas linhas se precisar de mais verbosidade
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        logging.getLogger().setLevel(logging.DEBUG)
    
    asyncio.run(main())

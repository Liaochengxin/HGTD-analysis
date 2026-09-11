//-----------------2025.12.31--------------------
//Tianyuan Zhang, IHEP, tyzhang@ihep.ac.cn

used to plot the Vbd and I-Ratio comparison for multiple batches of sensors, using data from both probe card and per-pad measurements. The script reads CSV files containing the relevant data, processes it, and generates comparison plots with fixed y-axis ranges for consistency across different batches.

#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <map>
#include <TGraphErrors.h>
#include <TGraph.h>
#include <TCanvas.h>
#include <TAxis.h>
#include <TLegend.h>
#include <TH1D.h>
#include <TH1F.h>
#include <TLine.h>
#include <TPaveText.h>
#include <TColor.h>
#include <TStyle.h>
#include <TString.h>
#include <iomanip>

TString NormalizeDir(TString dir) {
    if (!dir.EndsWith("/")) dir += "/";
    return dir;
}

TString GetProbeCardDir(const std::string& batch, const TString& defaultDir) {
    static const std::map<std::string, TString> batchDirs = {
        {"06", "./SQC/IHEP/csv/1st_50_pre/"},
        {"07", "./SQC/IHEP/csv/1st_50_pre/"},
        {"15", "./SQC/IHEP/csv/1st_50_pre/"},
        {"18", "./SQC/IHEP/csv/1st_50_post/"},
        {"21", "./SQC/IHEP/csv/1st_50_post/"},
        // {"31", "./SQC/IHEP/csv/2nd_50_pre/"},
        // {"33", "./SQC/IHEP/csv/2nd_50_pre/"},
        // {"36", "./SQC/IHEP/csv/2nd_50_pre/"}
    };

    std::string batchShort = std::to_string(std::stoi(batch));
    auto it = batchDirs.find(batchShort);
    if (it != batchDirs.end()) return NormalizeDir(it->second);
    return NormalizeDir(defaultDir);
}

void PlotSensorVbd_multibatches(TString defaultProbeCardDir = "./SQC/IHEP/csv/1st_50_pre/",
                             TString perPadDir = "./out/") {
    // ========== 全局样式设置 ==========
    gStyle->SetOptStat(0);
    
    // ========== 固定纵坐标范围设置（关键！）==========
    const double VBD_Y_MIN = 150.0;
    const double VBD_Y_MAX = 220.0;
    
    const double IRATIO_Y_MIN = 0.0;
    const double IRATIO_Y_MAX = 3.5;  // 稍微大一点容纳所有数据
    
    // ========== 配置区域 ==========
    // std::vector<std::string> batch_list  = {"06", "06", "06", "06", "06", "06", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "15", "15", "15", "15", "15"};
    // std::vector<std::string> wafer_list  = {"01", "02", "04", "05", "06", "14", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "14", "04", "06", "07", "11", "25"};
    // std::vector<std::string> sensor_list = {"02", "03", "03", "03", "11", "06", "02", "03", "02", "05", "02", "02", "03", "03", "12", "02", "03", "05", "03", "03", "08", "01", "02", "12"};
    // std::vector<std::string> batch_list  = {"06", "06", "06", "06", "06", "06", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "15", "15", "15", "15", "15", "18", "18", "18", "21", "21", "21", "31", "31", "33", "33", "33", "36"};
    // std::vector<std::string> wafer_list  = {"01", "02", "04", "05", "06", "14", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "14", "04", "06", "07", "11", "25", "01", "12", "25", "01", "12", "25", "22", "25", "01", "12", "25", "01"};
    // std::vector<std::string> sensor_list = {"02", "03", "03", "03", "11", "06", "02", "03", "02", "05", "02", "02", "03", "03", "12", "02", "03", "05", "03", "03", "08", "01", "02", "12", "07", "02", "07", "04", "02", "02", "03", "03", "02", "03", "02", "04"};
    // std::vector<std::string> batch_list  = {"18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "21"};
    // std::vector<std::string> wafer_list  = {"01", "02", "04", "06", "08", "10", "12", "14", "18", "20", "22", "25", "25"};
    // std::vector<std::string> sensor_list = {"03", "03", "09", "02", "03", "02", "01", "11", "05", "02", "02", "02", "02"};
    std::vector<std::string> batch_list  = {"06", "06", "06", "06", "06", "06", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "07", "15", "15", "15", "15", "15", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "18", "21", "21", "21", "21"};
    std::vector<std::string> wafer_list  = {"01", "02", "04", "05", "06", "14", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "14", "04", "06", "07", "11", "25", "01", "01", "02", "04", "06", "08", "10", "12", "12", "14", "18", "20", "22", "25", "25", "01", "11", "12", "25"};
    std::vector<std::string> sensor_list = {"02", "03", "03", "03", "11", "06", "02", "03", "02", "05", "02", "02", "03", "03", "12", "02", "03", "05", "03", "03", "08", "01", "02", "12", "03", "07", "03", "09", "02", "03", "02", "01", "02", "11", "05", "02", "02", "02", "07", "04", "01", "02", "02"};
    if (batch_list.size() != wafer_list.size() || batch_list.size() != sensor_list.size()) {
        std::cerr << "Error: batch_list, wafer_list, and sensor_list must have the same size!" << std::endl;
        return;
    }
    
    defaultProbeCardDir = NormalizeDir(defaultProbeCardDir);
    perPadDir = NormalizeDir(perPadDir);
    
    // ========== 数据存储 ==========
    std::vector<int> sensorIds;
    std::vector<double> probeMeans, probeRms, probeVbdMins, probeIRatios;
    std::vector<double> needleMeans, needleRms, needleVbdMins, needleIRatios;
    std::vector<std::string> labels, batchLabels;
    
    // ========== 数据读取 ==========
    for (size_t i = 0; i < batch_list.size(); ++i) {
        std::string batch = batch_list[i];
        std::string wafer = wafer_list[i];
        std::string sensor = sensor_list[i];
        
        std::string batchShort = std::to_string(std::stoi(batch));
        std::string waferShort = std::to_string(std::stoi(wafer));
        std::string sensorShort = std::to_string(std::stoi(sensor));
        std::string label = "B" + batchShort + "-W" + waferShort + "-P" + sensorShort;
        
        std::cout << "\n[" << i+1 << "/" << batch_list.size() << "] Processing " << label << "..." << std::endl;
        
        // Probe Card数据
        TString probeCardDir = GetProbeCardDir(batch, defaultProbeCardDir);
        TString probeFile = probeCardDir + Form("20WS001%s000%s.csv", batch.c_str(), wafer.c_str());
        double pMean = 0, pRms = 0, pMin = 0, pIRatio = 0;
        bool probeLoaded = false;
        
        std::ifstream csv1(probeFile.Data());
        if (csv1.is_open()) {
            std::string line;
            std::getline(csv1, line);
            while (std::getline(csv1, line)) {
                std::stringstream ss(line);
                std::string s, vbdAvg, vbdMn, vbdRm, vbdRmsOv, vbdStat, 
                           iAvg, iMx, iMn, iRat, fStatus;
                std::getline(ss, s, ',');
                if (std::stoi(s) != std::stoi(sensor)) continue;
                std::getline(ss, vbdAvg, ',');
                std::getline(ss, vbdMn, ',');
                std::getline(ss, vbdRm, ',');
                std::getline(ss, vbdRmsOv, ',');
                std::getline(ss, vbdStat, ',');
                std::getline(ss, iAvg, ',');
                std::getline(ss, iMx, ',');
                std::getline(ss, iMn, ',');
                std::getline(ss, iRat, ',');
                std::getline(ss, fStatus, ',');
                pMean = std::stod(vbdAvg);
                pMin = std::stod(vbdMn);
                pRms = std::stod(vbdRm);
                pIRatio = std::stod(iRat);
                probeLoaded = true;
                std::cout << "  Probe: Mean=" << pMean << " V, RMS=" << pRms << " V, Min=" << pMin << " V" << std::endl;
                break;
            }
            csv1.close();
        } else {
            std::cerr << "  Warning: Probe card file not found: " << probeFile << std::endl;
        }
        
        // Per-Pad数据
        TString perPadFile = perPadDir + Form("%s/SingleSensor_Report.csv", label.c_str());
        double nMean = 0, nRms = 0, nMin = 0, nIRatio = 0;
        bool needleLoaded = false;
        
        std::ifstream csv2(perPadFile.Data());
        if (csv2.is_open()) {
            std::string line;
            std::getline(csv2, line);
            while (std::getline(csv2, line)) {
                std::stringstream ss(line);
                std::string param, value, unit, status, threshold;
                std::getline(ss, param, ',');
                std::getline(ss, value, ',');
                std::getline(ss, unit, ',');
                std::getline(ss, status, ',');
                std::getline(ss, threshold, ',');
                if (param == "Mean Vbd (20°C)") nMean = std::stod(value);
                else if (param == "Min Vbd (20°C)") nMin = std::stod(value);
                else if (param == "Vbd RMS") nRms = std::stod(value);
                else if (param == "Leakage Current Ratio (inner)") nIRatio = std::stod(value);
            }
            csv2.close();
            needleLoaded = true;
            std::cout << "  Needle: Mean=" << nMean << " V, RMS=" << nRms << " V, Min=" << nMin << " V" << std::endl;
        } else {
            std::cerr << "  Warning: Per-Pad file not found: " << perPadFile << std::endl;
        }
        
        if (probeLoaded && needleLoaded) {
            sensorIds.push_back(i + 1);
            probeMeans.push_back(pMean);
            probeRms.push_back(pRms);
            probeVbdMins.push_back(pMin);
            probeIRatios.push_back(pIRatio);
            needleMeans.push_back(nMean);
            needleRms.push_back(nRms);
            needleVbdMins.push_back(nMin);
            needleIRatios.push_back(nIRatio);
            labels.push_back(label);
            batchLabels.push_back("B" + batch);
        }
    }
    
    int nPoints = sensorIds.size();
    if (nPoints == 0) {
        std::cerr << "\nNo valid data loaded!" << std::endl;
        return;
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "Successfully loaded " << nPoints << " / " << batch_list.size() << " sensors." << std::endl;
    std::cout << "========================================" << std::endl;
    
    // ========== 创建图表数据 ==========
    TGraphErrors *graphProbe = new TGraphErrors(nPoints);
    TGraphErrors *graphNeedle = new TGraphErrors(nPoints);
    TGraph *graphProbeMin = new TGraph(nPoints);
    TGraph *graphNeedleMin = new TGraph(nPoints);
    
    for (int i = 0; i < nPoints; ++i) {
        double x = i + 1;
        graphProbe->SetPoint(i, x, probeMeans[i]);
        graphProbe->SetPointError(i, 0, probeRms[i]);
        graphNeedle->SetPoint(i, x, needleMeans[i]);
        graphNeedle->SetPointError(i, 0, needleRms[i]);
        graphProbeMin->SetPoint(i, x, probeVbdMins[i]);
        graphNeedleMin->SetPoint(i, x, needleVbdMins[i]);
    }
    
    // ========== Vbd对比图（使用固定范围）==========
    TCanvas *canvas1 = new TCanvas("canvas1", "Sensor Vbd Comparison", 1400, 800);
    canvas1->SetBottomMargin(0.25);
    canvas1->SetLeftMargin(0.12);
    canvas1->SetRightMargin(0.08);

    // 关键修复：直接使用常量，不修改！
    TH1F *frame1 = new TH1F("frame1", "", nPoints, 0.5, nPoints + 0.5);
    frame1->SetMinimum(VBD_Y_MIN);  // 固定150
    frame1->SetMaximum(VBD_Y_MAX);  // 固定220
    frame1->GetYaxis()->SetTitle("Vbd [V]");
    frame1->GetYaxis()->SetTitleSize(0.05);
    frame1->GetYaxis()->SetTitleFont(42);
    frame1->GetYaxis()->SetLabelSize(0.04);
    frame1->GetXaxis()->SetTitle("Sensor Number");
    frame1->GetXaxis()->SetTitleSize(0.05);
    frame1->GetXaxis()->SetTitleFont(42);
    frame1->GetXaxis()->SetTitleOffset(1.8);
    frame1->Draw("");

    // X轴标签设置
    TAxis *xAxis = frame1->GetXaxis();
    xAxis->SetNdivisions(nPoints, 0, 0, kFALSE);
    for (int i = 0; i < nPoints; ++i) {
        xAxis->SetBinLabel(i + 1, labels[i].c_str());
    }
    xAxis->LabelsOption("u");
    xAxis->SetLabelSize(0.04);
    xAxis->SetLabelFont(40);
    xAxis->SetLabelOffset(0.015);

    // 绘制图形
    graphProbe->SetMarkerStyle(21);
    graphProbe->SetMarkerColor(kBlue);
    graphProbe->SetLineColor(kBlue);
    graphProbe->SetLineWidth(2);
    graphProbe->Draw("P SAME");

    graphNeedle->SetMarkerStyle(21);
    graphNeedle->SetMarkerColor(kRed);
    graphNeedle->SetLineColor(kRed);
    graphNeedle->SetLineWidth(2);
    graphNeedle->Draw("P SAME");

    graphProbeMin->SetMarkerStyle(20);
    graphProbeMin->SetMarkerColor(kGreen);
    graphProbeMin->SetMarkerSize(1.5);
    graphProbeMin->Draw("P SAME");

    graphNeedleMin->SetMarkerStyle(20);
    graphNeedleMin->SetMarkerColor(kBlack);
    graphNeedleMin->SetMarkerSize(1.5);
    graphNeedleMin->Draw("P SAME");

    // 参考线
    TLine *line165 = new TLine(0.5, 165, nPoints + 0.5, 165);
    line165->SetLineColor(kBlack);
    line165->SetLineStyle(2);
    line165->Draw();
    
    TLine *line195 = new TLine(0.5, 195, nPoints + 0.5, 195);
    line195->SetLineColor(kBlack);
    line195->SetLineStyle(2);
    line195->Draw();

    // 图例
    TLegend *legend1 = new TLegend(0.15, 0.02, 0.85, 0.12);
    legend1->SetNColumns(4);
    legend1->SetColumnSeparation(0.1);
    legend1->SetMargin(0.15);
    legend1->SetTextSize(0.04);
    legend1->SetFillStyle(0);
    legend1->SetBorderSize(0);
    legend1->AddEntry(graphProbe, "Probe Card Mean", "lp");
    legend1->AddEntry(graphNeedle, "Per-Pad Mean", "lp");
    legend1->AddEntry(graphProbeMin, "Probe Card Min", "p");
    legend1->AddEntry(graphNeedleMin, "Per-Pad Min", "p");
    legend1->Draw();
    
    canvas1->SaveAs("MultiBatch_VbdComparison.png");
    
    // ========== VbdMin分布图（使用相同固定范围）==========
    std::map<std::string, std::vector<double>> batchProbeMin;
    std::map<std::string, std::vector<double>> batchNeedleMin;
    
    for (int i = 0; i < nPoints; ++i) {
        batchProbeMin[batchLabels[i]].push_back(probeVbdMins[i]);
        batchNeedleMin[batchLabels[i]].push_back(needleVbdMins[i]);
    }
    
    int nBatches = batchProbeMin.size();
    
    TCanvas *canvas2 = new TCanvas("canvas2", "VbdMin Distribution by Batch", 1000, 600);
    
    TH1D *histProbeMin = new TH1D("histProbeMin", "VbdMin Distribution by Batch;Batch;VbdMin [V]", 
                                   nBatches * 2, 0, nBatches * 2);
    TH1D *histNeedleMin = new TH1D("histNeedleMin", "VbdMin Distribution by Batch;Batch;VbdMin [V]", 
                                    nBatches * 2, 0, nBatches * 2);
    
    int bin = 1;
    for (auto& batch : batchProbeMin) {
        double sumProbe = 0, sumNeedle = 0;
        for (auto& v : batch.second) sumProbe += v;
        for (auto& v : batchNeedleMin[batch.first]) sumNeedle += v;
        double avgProbe = sumProbe / batch.second.size();
        double avgNeedle = sumNeedle / batchNeedleMin[batch.first].size();
        histProbeMin->SetBinContent(bin, avgProbe);
        histNeedleMin->SetBinContent(bin + 1, avgNeedle);
        histProbeMin->GetXaxis()->SetBinLabel(bin, (batch.first + "(P)").c_str());
        histProbeMin->GetXaxis()->SetBinLabel(bin + 1, (batch.first + "(N)").c_str());
        bin += 2;
    }
    
    Int_t transparentBlue = TColor::GetColorTransparent(kBlue, 0.5);
    Int_t transparentRed = TColor::GetColorTransparent(kRed, 0.5);
    
    histProbeMin->SetFillColor(transparentBlue);
    histProbeMin->SetLineColor(kBlue);
    histProbeMin->SetLineWidth(2);
    histProbeMin->SetStats(kFALSE);
    histProbeMin->SetMinimum(VBD_Y_MIN);  // 固定150（与VbdComparison一致）
    histProbeMin->SetMaximum(VBD_Y_MAX);  // 固定220（与VbdComparison一致）
    histProbeMin->Draw("BAR");
    
    histNeedleMin->SetFillColor(transparentRed);
    histNeedleMin->SetLineColor(kRed);
    histNeedleMin->SetLineWidth(2);
    histNeedleMin->SetStats(kFALSE);
    histNeedleMin->Draw("BAR SAME");
    
    TLine *line165_2 = new TLine(0, 165, nBatches * 2, 165);
    line165_2->SetLineColor(kBlack);
    line165_2->SetLineStyle(2);
    line165_2->Draw();
    
    TLine *line195_2 = new TLine(0, 195, nBatches * 2, 195);
    line195_2->SetLineColor(kBlack);
    line195_2->SetLineStyle(2);
    line195_2->Draw();
    
    TLegend *legend2 = new TLegend(0.7, 0.8, 0.9, 0.9);
    legend2->AddEntry(histProbeMin, "Probe Card (Avg)", "f");
    legend2->AddEntry(histNeedleMin, "Per-Pad (Avg)", "f");
    legend2->Draw();
    
    canvas2->SaveAs("MultiBatch_VbdMinDistribution.png");
    
    // ========== I-Ratio对比图（使用固定范围）==========
    TGraph *graphProbeI = new TGraph(nPoints);
    TGraph *graphNeedleI = new TGraph(nPoints);
    
    for (int i = 0; i < nPoints; ++i) {
        graphProbeI->SetPoint(i, i + 1, probeIRatios[i]);
        graphNeedleI->SetPoint(i, i + 1, needleIRatios[i]);
    }
    
    TCanvas *canvas3 = new TCanvas("canvas3", "I-Ratio Comparison", 1400, 600);
    canvas3->SetBottomMargin(0.25);
    canvas3->SetLeftMargin(0.12);
    canvas3->SetRightMargin(0.08);

    // 关键修复：直接使用常量，不修改！
    TH1F *frame3 = new TH1F("frame3", "", nPoints, 0.5, nPoints + 0.5);
    frame3->SetMinimum(IRATIO_Y_MIN);  // 固定0
    frame3->SetMaximum(IRATIO_Y_MAX);  // 固定3.5
    frame3->GetYaxis()->SetTitle("I-Ratio");
    frame3->GetYaxis()->SetTitleSize(0.05);
    frame3->GetYaxis()->SetTitleFont(42);
    frame3->GetYaxis()->SetLabelSize(0.04);
    frame3->GetXaxis()->SetTitle("Sensor Number");
    frame3->GetXaxis()->SetTitleSize(0.05);
    frame3->GetXaxis()->SetTitleFont(42);
    frame3->GetXaxis()->SetTitleOffset(1.8);
    frame3->Draw("");

    // X轴设置
    TAxis *xAxis3 = frame3->GetXaxis();
    xAxis3->SetNdivisions(nPoints, 0, 0, kFALSE);
    for (int i = 0; i < nPoints; ++i) {
        xAxis3->SetBinLabel(i + 1, labels[i].c_str());
    }
    xAxis3->LabelsOption("u");
    xAxis3->SetLabelSize(0.06);
    xAxis3->SetLabelFont(40);
    xAxis3->SetLabelOffset(0.015);

    // 绘制图形
    graphProbeI->SetMarkerStyle(20);
    graphProbeI->SetMarkerColor(kBlue);
    graphProbeI->SetMarkerSize(1.5);
    graphProbeI->Draw("P SAME");

    graphNeedleI->SetMarkerStyle(20);
    graphNeedleI->SetMarkerColor(kRed);
    graphNeedleI->SetMarkerSize(1.5);
    graphNeedleI->Draw("P SAME");

    // 参考线
    TLine *line3 = new TLine(0.5, 3, nPoints + 0.5, 3);
    line3->SetLineColor(kBlack);
    line3->SetLineStyle(2);
    line3->Draw();
    
    // 图例
    TLegend *legend3 = new TLegend(0.3, 0.02, 0.7, 0.12);
    legend3->SetNColumns(2);
    legend3->SetColumnSeparation(0.2);
    legend3->SetMargin(0.15);
    legend3->SetTextSize(0.04);
    legend3->SetFillStyle(0);
    legend3->SetBorderSize(0);
    legend3->AddEntry(graphProbeI, "Probe Card", "p");
    legend3->AddEntry(graphNeedleI, "Per-Pad", "p");
    legend3->Draw();
    
    canvas3->SaveAs("MultiBatch_IRatioComparison.png");
    
    // ========== 统计摘要 ==========
    std::cout << "\n========================================" << std::endl;
    std::cout << "Statistical Summary" << std::endl;
    std::cout << "========================================" << std::endl;
    
    double totalProbeMean = 0, totalNeedleMean = 0;
    double totalProbeMin = 0, totalNeedleMin = 0;
    
    for (int i = 0; i < nPoints; ++i) {
        totalProbeMean += probeMeans[i];
        totalNeedleMean += needleMeans[i];
        totalProbeMin += probeVbdMins[i];
        totalNeedleMin += needleVbdMins[i];
        double diffMean = needleMeans[i] - probeMeans[i];
        double diffPercent = (diffMean / probeMeans[i]) * 100;
        std::cout << labels[i] << ":" << std::endl;
        std::cout << "  Mean Vbd: Probe=" << probeMeans[i] << " V, Needle=" << needleMeans[i] 
                  << " V, Diff=" << diffMean << " V (" << diffPercent << "%)" << std::endl;
    }
    
    std::cout << "\nOverall Average:" << std::endl;
    std::cout << "  Mean Vbd: Probe=" << totalProbeMean/nPoints << " V, Needle=" 
              << totalNeedleMean/nPoints << " V" << std::endl;
    std::cout << "  Min Vbd:  Probe=" << totalProbeMin/nPoints << " V, Needle=" 
              << totalNeedleMin/nPoints << " V" << std::endl;
    
    std::cout << "\nPlots saved:" << std::endl;
    std::cout << "  1. MultiBatch_VbdComparison.png" << std::endl;
    std::cout << "  2. MultiBatch_VbdMinDistribution.png" << std::endl;
    std::cout << "  3. MultiBatch_IRatioComparison.png" << std::endl;
    std::cout << "========================================" << std::endl;
}

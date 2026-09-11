//-----------------2025.12.31--------------------
//Tianyuan Zhang, IHEP, tyzhang@ihep.ac.cn

used to determine the breakdown voltage (Vbd) and leakage current (I) characteristics of pixels
sum the I-V curves of 15 pixels in a column, and plot the summed I-V curve for analysis.

#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <iomanip>
#include <TGraph.h>
#include <TCanvas.h>
#include <TAxis.h>
#include <TLegend.h>
#include <TLine.h>
#include <TColor.h>
#include <TLatex.h>

using namespace std;

struct PixelData {
    int index;
    vector<double> voltages;
    vector<double> currents;
};

string trim(const string& str) {
    size_t first = str.find_first_not_of(" \t\r\n");
    if (first == string::npos) return "";
    size_t last = str.find_last_not_of(" \t\r\n");
    return str.substr(first, last - first + 1);
}

vector<string> splitCSV(const string& line) {
    vector<string> tokens;
    string token;
    bool inQuotes = false;
    for (char c : line) {
        if (c == '"') inQuotes = !inQuotes;
        else if (c == ',' && !inQuotes) {
            tokens.push_back(trim(token));
            token.clear();
        } else token += c;
    }
    tokens.push_back(trim(token));
    return tokens;
}

bool readCSV(const string& filepath, PixelData& data) {
    ifstream file(filepath);
    if (!file.is_open()) return false;
    
    string line;
    if (!getline(file, line)) return false;
    
    vector<string> headers = splitCSV(line);
    int vIdx = -1, cIdx = -1;
    for (size_t i = 0; i < headers.size(); i++) {
        string h = headers[i];
        transform(h.begin(), h.end(), h.begin(), ::tolower);
        if (h.find("voltage") != string::npos) vIdx = i;
        if (h.find("current") != string::npos && h.find("meas") == string::npos) cIdx = i;
    }
    if (vIdx == -1 || cIdx == -1) return false;
    
    while (getline(file, line)) {
        vector<string> cols = splitCSV(line);
        if (cols.size() <= max(vIdx, cIdx)) continue;
        try {
            double v = stod(cols[vIdx]);
            double c = stod(cols[cIdx]);
            data.voltages.push_back(v);
            data.currents.push_back(c);
        } catch (...) { continue; }
    }
    return !data.voltages.empty();
}

// 生成红色系渐变：从浅红/粉红到深红
void getRedGradient(int index, int total, int& r, int& g, int& b) {
    double t = (double)index / (total - 1); // 0.0 到 1.0
    
    // 浅红 (255, 200, 200) -> 标准红 (255, 0, 0) -> 深红 (139, 0, 0)
    if (t < 0.5) {
        // 浅红到标准红
        double localT = t / 0.5;
        r = 255;
        g = (int)(200 * (1 - localT));
        b = (int)(200 * (1 - localT));
    } else {
        // 标准红到深红
        double localT = (t - 0.5) / 0.5;
        r = (int)(255 - (255 - 139) * localT); // 255 -> 139
        g = 0;
        b = 0;
    }
}

void plotPerPadColumn(int column, const string& inputDir = ".", const string& outputName = "") {
    cout << "处理第 " << column << " 列" << endl;
    
    vector<int> pixelIndices;
    for (int i = column; i <= 225; i += 15) pixelIndices.push_back(i);
    
    cout << "包含像素: ";
    for (size_t i = 0; i < pixelIndices.size(); i++) {
        cout << pixelIndices[i];
        if (i < pixelIndices.size() - 1) cout << ", ";
    }
    cout << endl;
    
    vector<PixelData> pixels;
    map<double, vector<double>> voltageMap;
    int processed = 0;
    
    for (int idx : pixelIndices) {
        string filepath = inputDir + "/1-" + to_string(idx) + ".csv";
        PixelData data;
        data.index = idx;
        
        if (readCSV(filepath, data)) {
            pixels.push_back(data);
            for (size_t i = 0; i < data.voltages.size(); i++) {
                voltageMap[data.voltages[i]].push_back(data.currents[i]);
            }
            processed++;
            cout << "  1-" << idx << ".csv: " << data.voltages.size() << " 点" << endl;
        }
    }
    
    if (processed == 0) {
        cerr << "错误: 没有成功处理任何文件!" << endl;
        return;
    }
    cout << "成功处理 " << processed << "/15 个像素" << endl;
    
    vector<double> voltageOrder = pixels[0].voltages;
    
    // 计算求和曲线（取负号，单位保持A）
    vector<double> sumV_pos, sumI_pos;
    for (double v : voltageOrder) {
        auto it = voltageMap.find(v);
        if (it != voltageMap.end()) {
            double total = 0;
            for (double c : it->second) total += c;
            sumV_pos.push_back(-v);
            sumI_pos.push_back(-total);
        }
    }
    
    // ========== 生成PNG图片 ==========
    string pngName;
    if (outputName.empty()) {
        pngName = inputDir + "/column_" + to_string(column) + "_plot.png";
    } else {
        pngName = inputDir + "/" + outputName;
    }
    
    TCanvas* c1 = new TCanvas("c1", ("Column " + to_string(column) + " IV Curves").c_str(), 1200, 800);
    c1->SetGrid();
    c1->SetLeftMargin(0.14);
    c1->SetBottomMargin(0.12);
    c1->SetLogy();
    
    // 绘制像素曲线（红色系渐变）
    vector<TGraph*> pixelGraphs;
    for (size_t pIdx = 0; pIdx < pixels.size(); pIdx++) {
        const auto& p = pixels[pIdx];
        vector<double> v_pos, i_pos;
        for (size_t i = 0; i < p.voltages.size(); i++) {
            v_pos.push_back(-p.voltages[i]);
            i_pos.push_back(-p.currents[i]);
        }
        
        TGraph* g = new TGraph(v_pos.size(), v_pos.data(), i_pos.data());
        
        int r, gr, b;
        getRedGradient(pIdx, pixels.size(), r, gr, b);
        g->SetLineColor(TColor::GetColor(r, gr, b));
        g->SetLineWidth(2);
        pixelGraphs.push_back(g);
    }
    
    // 第一个像素设置标题和坐标轴
    pixelGraphs[0]->SetTitle(("Column " + to_string(column) + " IV Curves;Voltage (V);Current (A)").c_str());
    pixelGraphs[0]->GetXaxis()->SetTitleSize(0.04);
    pixelGraphs[0]->GetYaxis()->SetTitleSize(0.04);
    pixelGraphs[0]->GetXaxis()->SetLabelSize(0.03);
    pixelGraphs[0]->GetYaxis()->SetLabelSize(0.03);
    pixelGraphs[0]->GetXaxis()->SetRangeUser(0, 230);
    pixelGraphs[0]->GetYaxis()->SetRangeUser(1e-11, 1e-4);
    pixelGraphs[0]->Draw("AL");
    
    // 画其余像素曲线
    for (size_t i = 1; i < pixelGraphs.size(); i++) {
        pixelGraphs[i]->Draw("L SAME");
    }
    
    // 画求和曲线（蓝色，粗线，带标记）
    TGraph* sumGraph = new TGraph(sumV_pos.size(), sumV_pos.data(), sumI_pos.data());
    sumGraph->SetLineColor(kBlue);
    sumGraph->SetLineWidth(4);
    sumGraph->SetMarkerStyle(20);
    sumGraph->SetMarkerColor(kBlue);
    sumGraph->SetMarkerSize(1.2);
    sumGraph->Draw("PL SAME");
    
    // 参考线 0.5uA=0.5e-6A 和 7.5uA=7.5e-6A
    double xMin = *min_element(sumV_pos.begin(), sumV_pos.end());
    double xMax = *max_element(sumV_pos.begin(), sumV_pos.end());
    
    TLine* line05 = new TLine(xMin, 0.5e-6, xMax, 0.5e-6);
    line05->SetLineColor(kBlack);
    line05->SetLineStyle(2);
    line05->SetLineWidth(2);
    line05->Draw();
    
    TLine* line75 = new TLine(xMin, 7.5e-6, xMax, 7.5e-6);
    line75->SetLineColor(kBlack);
    line75->SetLineStyle(2);
    line75->SetLineWidth(2);
    line75->Draw();
    // 在参考线附近添加文字标签
    TLatex* latex = new TLatex();
    latex->SetTextSize(0.03);
    latex->SetTextFont(42);
    
    // 0.5 uA 标签（放在线右侧，稍微偏上）
    latex->SetTextColor(kBlack);
    latex->DrawLatex(xMax - (xMax - xMin) * 0.05, 0.5e-6 * 1.5, "0.5 #muA");
    
    // 7.5 uA 标签（放在线右侧，稍微偏上）
    latex->SetTextColor(kBlack);
    latex->DrawLatex(xMax - (xMax - xMin) * 0.05, 7.5e-6 * 1.5, "7.5 #muA");
    
    // 图例放在左上角
    //TLegend* leg = new TLegend(0.15, 0.65, 0.40, 0.88);
    TLegend* leg = new TLegend(0.66, 0.15, 0.89, 0.38);
    leg->SetFillStyle(1001);
    leg->SetFillColor(kWhite);
    leg->SetBorderSize(1);
    leg->AddEntry(pixelGraphs[0], Form("Pixel %d", pixels[0].index), "l");
    leg->AddEntry(pixelGraphs[pixels.size()-1], Form("Pixel %d", pixels.back().index), "l");
    leg->AddEntry(sumGraph, "Sum", "pl");
    leg->AddEntry(line05, "0.5 #muA", "l");
    leg->AddEntry(line75, "7.5 #muA", "l");
    leg->Draw();
    
    // 保存PNG
    c1->SaveAs(pngName.c_str());
    cout << "PNG图片保存至: " << pngName << endl;
    
    // ========== 生成CSV文件 ==========
    string csvName = inputDir + "/column_" + to_string(column) + "_sum.csv";
    ofstream csv(csvName);
    csv << "Voltage(V),Total_Current(A)" << endl;
    csv << scientific << setprecision(6);
    for (size_t i = 0; i < voltageOrder.size(); i++) {
        double v = voltageOrder[i];
        auto it = voltageMap.find(v);
        if (it != voltageMap.end()) {
            double total = 0;
            for (double c : it->second) total += c;
            csv << v << "," << total << endl;
        }
    }
    csv.close();
    cout << "CSV文件保存至: " << csvName << endl;
    
    delete c1;
}

void process_perpad(int column, const string& inputDir = ".", const string& outputFile = "") {
    plotPerPadColumn(column, inputDir, outputFile);
}